"""
Tests for app/services/sync_executor.py

Covers the worker-execution half of each outbound scenario:
  - create  → calls QBO, sets sync_status='complete', external_invoice_id, saves api_log
  - update  → calls QBO, updates sync_token, sets sync_status='complete', saves api_log
  - delete  → calls QBO, sets sync_status='complete', saves api_log
  - void    → calls QBO, sets sync_status='complete', saves api_log

Idempotency guard (create):
  - If invoice already has external_invoice_id the QBO call is skipped entirely
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.integrations.quickbooks_client import QBOResult
from app.models.models import ApiLog, InvoiceHistory, SyncJob
from app.services.sync_executor import execute_job
from tests.conftest import make_execute_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job(operation: str) -> MagicMock:
    job = MagicMock(spec=SyncJob)
    job.invoice_id = 100
    job.company_id = 1
    job.operation = operation
    return job


def _added_types(db) -> list[str]:
    return [type(c.args[0]).__name__ for c in db.add.call_args_list]


# ---------------------------------------------------------------------------
# Shared QBO mock responses
# ---------------------------------------------------------------------------

QBO_CREATE_RESPONSE = QBOResult(
    data={"Invoice": {"Id": "QBO_NEW_001", "SyncToken": "0"}},
    request_body={"DocNumber": "INV-2026-000000100"},
)

QBO_UPDATE_RESPONSE = QBOResult(
    data={"Invoice": {"Id": "QBO_001", "SyncToken": "7"}},
    request_body={"Id": "QBO_001", "SyncToken": "5", "sparse": True},
)

QBO_DELETE_RESPONSE = QBOResult(
    data={"Invoice": {"Id": "QBO_001", "domain": "QBO", "status": "Deleted"}},
    request_body={"Id": "QBO_001", "SyncToken": "5"},
)

QBO_VOID_RESPONSE = QBOResult(
    data={"Invoice": {"Id": "QBO_001", "PrivateNote": "Voided"}},
    request_body={"Id": "QBO_001", "SyncToken": "5"},
)


# ---------------------------------------------------------------------------
# execute_job — create
# ---------------------------------------------------------------------------


class TestExecuteCreate:
    def _setup(self, db, invoice, company, invoice_item):
        db.execute.side_effect = [
            make_execute_result(scalar_one=invoice),
            make_execute_result(scalar_one=company),
            make_execute_result(scalars_all=[invoice_item]),
        ]

    def test_sets_external_invoice_id_after_sync(self, db, synced_invoice, company, invoice_item):
        """After a successful QBO create the invoice gets the QBO-assigned Id."""
        synced_invoice.external_invoice_id = None  # not yet synced
        self._setup(db, synced_invoice, company, invoice_item)

        with patch("app.services.sync_executor.QuickBooksClient") as MockClient:
            MockClient.return_value.create_invoice.return_value = QBO_CREATE_RESPONSE
            MockClient.return_value._invoice_base_url = "http://mock/invoice"

            execute_job(_make_job("create"), db)

        assert synced_invoice.external_invoice_id == "QBO_NEW_001"

    def test_sets_sync_status_complete(self, db, synced_invoice, company, invoice_item):
        synced_invoice.external_invoice_id = None
        self._setup(db, synced_invoice, company, invoice_item)

        with patch("app.services.sync_executor.QuickBooksClient") as MockClient:
            MockClient.return_value.create_invoice.return_value = QBO_CREATE_RESPONSE
            MockClient.return_value._invoice_base_url = "http://mock/invoice"

            execute_job(_make_job("create"), db)

        assert synced_invoice.sync_status == "complete"

    def test_saves_outbound_api_log(self, db, synced_invoice, company, invoice_item):
        """execute_job 'create' writes an outbound ApiLog entry."""
        synced_invoice.external_invoice_id = None
        self._setup(db, synced_invoice, company, invoice_item)

        with patch("app.services.sync_executor.QuickBooksClient") as MockClient:
            MockClient.return_value.create_invoice.return_value = QBO_CREATE_RESPONSE
            MockClient.return_value._invoice_base_url = "http://mock/invoice"

            execute_job(_make_job("create"), db)

        assert "ApiLog" in _added_types(db)

    def test_saves_invoice_history(self, db, synced_invoice, company, invoice_item):
        synced_invoice.external_invoice_id = None
        self._setup(db, synced_invoice, company, invoice_item)

        with patch("app.services.sync_executor.QuickBooksClient") as MockClient:
            MockClient.return_value.create_invoice.return_value = QBO_CREATE_RESPONSE
            MockClient.return_value._invoice_base_url = "http://mock/invoice"

            execute_job(_make_job("create"), db)

        assert "InvoiceHistory" in _added_types(db)

    def test_skips_qbo_call_if_already_synced(self, db, synced_invoice, company, invoice_item):
        """If external_invoice_id is already set, the QBO create call is skipped."""
        # synced_invoice already has external_invoice_id="QBO_001"
        self._setup(db, synced_invoice, company, invoice_item)

        with patch("app.services.sync_executor.QuickBooksClient") as MockClient:
            execute_job(_make_job("create"), db)
            MockClient.return_value.create_invoice.assert_not_called()


# ---------------------------------------------------------------------------
# execute_job — update
# ---------------------------------------------------------------------------


class TestExecuteUpdate:
    def _setup(self, db, invoice, company):
        db.execute.side_effect = [
            make_execute_result(scalar_one=invoice),
            make_execute_result(scalar_one=company),
        ]

    def test_updates_sync_token_from_qbo_response(self, db, synced_invoice, company):
        """After a successful update the local sync_token matches QBO's."""
        self._setup(db, synced_invoice, company)

        with patch("app.services.sync_executor.QuickBooksClient") as MockClient:
            MockClient.return_value.update_invoice.return_value = QBO_UPDATE_RESPONSE
            MockClient.return_value._invoice_base_url = "http://mock/invoice"

            execute_job(_make_job("update"), db)

        assert synced_invoice.sync_token == "7"

    def test_sets_sync_status_complete(self, db, synced_invoice, company):
        self._setup(db, synced_invoice, company)

        with patch("app.services.sync_executor.QuickBooksClient") as MockClient:
            MockClient.return_value.update_invoice.return_value = QBO_UPDATE_RESPONSE
            MockClient.return_value._invoice_base_url = "http://mock/invoice"

            execute_job(_make_job("update"), db)

        assert synced_invoice.sync_status == "complete"

    def test_saves_outbound_api_log(self, db, synced_invoice, company):
        self._setup(db, synced_invoice, company)

        with patch("app.services.sync_executor.QuickBooksClient") as MockClient:
            MockClient.return_value.update_invoice.return_value = QBO_UPDATE_RESPONSE
            MockClient.return_value._invoice_base_url = "http://mock/invoice"

            execute_job(_make_job("update"), db)

        assert "ApiLog" in _added_types(db)


# ---------------------------------------------------------------------------
# execute_job — delete
# ---------------------------------------------------------------------------


class TestExecuteDelete:
    def _setup(self, db, invoice, company):
        db.execute.side_effect = [
            make_execute_result(scalar_one=invoice),
            make_execute_result(scalar_one=company),
        ]

    def test_sets_sync_status_complete(self, db, synced_invoice, company):
        self._setup(db, synced_invoice, company)

        with patch("app.services.sync_executor.QuickBooksClient") as MockClient:
            MockClient.return_value.delete_invoice.return_value = QBO_DELETE_RESPONSE
            MockClient.return_value._invoice_base_url = "http://mock/invoice"

            execute_job(_make_job("delete"), db)

        assert synced_invoice.sync_status == "complete"

    def test_saves_outbound_api_log(self, db, synced_invoice, company):
        self._setup(db, synced_invoice, company)

        with patch("app.services.sync_executor.QuickBooksClient") as MockClient:
            MockClient.return_value.delete_invoice.return_value = QBO_DELETE_RESPONSE
            MockClient.return_value._invoice_base_url = "http://mock/invoice"

            execute_job(_make_job("delete"), db)

        assert "ApiLog" in _added_types(db)

    def test_saves_invoice_history(self, db, synced_invoice, company):
        self._setup(db, synced_invoice, company)

        with patch("app.services.sync_executor.QuickBooksClient") as MockClient:
            MockClient.return_value.delete_invoice.return_value = QBO_DELETE_RESPONSE
            MockClient.return_value._invoice_base_url = "http://mock/invoice"

            execute_job(_make_job("delete"), db)

        assert "InvoiceHistory" in _added_types(db)


# ---------------------------------------------------------------------------
# execute_job — void
# ---------------------------------------------------------------------------


class TestExecuteVoid:
    def _setup(self, db, invoice, company):
        db.execute.side_effect = [
            make_execute_result(scalar_one=invoice),
            make_execute_result(scalar_one=company),
        ]

    def test_sets_sync_status_complete(self, db, synced_invoice, company):
        self._setup(db, synced_invoice, company)

        with patch("app.services.sync_executor.QuickBooksClient") as MockClient:
            MockClient.return_value.void_invoice.return_value = QBO_VOID_RESPONSE
            MockClient.return_value._invoice_base_url = "http://mock/invoice"

            execute_job(_make_job("void"), db)

        assert synced_invoice.sync_status == "complete"

    def test_saves_outbound_api_log(self, db, synced_invoice, company):
        self._setup(db, synced_invoice, company)

        with patch("app.services.sync_executor.QuickBooksClient") as MockClient:
            MockClient.return_value.void_invoice.return_value = QBO_VOID_RESPONSE
            MockClient.return_value._invoice_base_url = "http://mock/invoice"

            execute_job(_make_job("void"), db)

        assert "ApiLog" in _added_types(db)

    def test_saves_invoice_history(self, db, synced_invoice, company):
        self._setup(db, synced_invoice, company)

        with patch("app.services.sync_executor.QuickBooksClient") as MockClient:
            MockClient.return_value.void_invoice.return_value = QBO_VOID_RESPONSE
            MockClient.return_value._invoice_base_url = "http://mock/invoice"

            execute_job(_make_job("void"), db)

        assert "InvoiceHistory" in _added_types(db)
