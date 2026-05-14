"""
Tests for app/services/sync_executor.py

Covers the worker-execution half of each outbound scenario:
  - create  → calls QBO, sets sync_status='complete', external_invoice_id, saves api_log
  - update  → calls QBO, updates sync_token, sets sync_status='complete', saves api_log
  - delete  → calls QBO, sets sync_status='complete', saves api_log
  - void    → calls QBO, sets sync_status='complete', saves api_log

Idempotency guards on create:
  - If invoice already has external_invoice_id the QBO call is skipped entirely
  - On retry attempts (job.attempts > 0), QBO is queried by DocNumber first to
    detect a successful prior write whose response was lost (timeout-after-write).

Conflict detection on update:
  - When QBO returns 400 and refetch shows divergent state, a ConflictError is
    raised and the invoice is flagged sync_status='conflict'.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.integrations.quickbooks_client import QBOResult
from app.models.models import InvoiceHistory, SyncJob
from app.services.exceptions import ConflictError
from app.services.sync_executor import execute_job
from tests.conftest import make_execute_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job(operation: str, attempts: int = 0) -> MagicMock:
    job = MagicMock(spec=SyncJob)
    job.invoice_id = 100
    job.company_id = 1
    job.operation = operation
    job.attempts = attempts
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

    def test_sets_external_invoice_id_after_sync(
        self, db, synced_invoice, company, invoice_item
    ):
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

    def test_skips_qbo_call_if_already_synced(
        self, db, synced_invoice, company, invoice_item
    ):
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


# ---------------------------------------------------------------------------
# execute_job — create — reconciliation on retry (timeout-after-write)
# ---------------------------------------------------------------------------


def _patch_create_client(qbo_create_response, query_response):
    """Helper context manager that mocks the QBO client for a create flow."""
    patcher = patch("app.services.sync_executor.QuickBooksClient")
    MockClient = patcher.start()
    MockClient.return_value.create_invoice.return_value = qbo_create_response
    MockClient.return_value.query_invoice_by_doc_number.return_value = query_response
    MockClient.return_value.invoice_base_url = "http://mock/invoice"
    MockClient.return_value._invoice_base_url = "http://mock/invoice"
    MockClient.return_value.query_url = "http://mock/query"
    return patcher, MockClient


class TestExecuteCreateReconciliation:
    """
    On the first attempt (attempts=0) the executor MUST NOT call the query API:
    a fresh create has no chance of being a duplicate.

    On a retry attempt (attempts>0) the executor MUST query QBO by DocNumber
    first. If a match is found, it links the local invoice to the existing QBO
    invoice without re-creating; if no match is found, it falls through to
    create as normal.

    This protects against the timeout-after-write edge case: the previous
    attempt may have succeeded server-side but lost the response in transit.
    """

    def _setup(self, db, invoice, company, invoice_item):
        invoice.external_invoice_id = None
        invoice.invoice_number = "INV-2026-000000100"
        db.execute.side_effect = [
            make_execute_result(scalar_one=invoice),
            make_execute_result(scalar_one=company),
            make_execute_result(scalars_all=[invoice_item]),
        ]

    def test_first_attempt_skips_query_and_creates(
        self, db, synced_invoice, company, invoice_item
    ):
        """attempts=0 → no query call; creates directly."""
        self._setup(db, synced_invoice, company, invoice_item)
        patcher, MockClient = _patch_create_client(
            QBO_CREATE_RESPONSE,
            QBOResult(data={"QueryResponse": {"Invoice": [], "totalCount": 0}}),
        )
        try:
            execute_job(_make_job("create", attempts=0), db)
        finally:
            patcher.stop()

        MockClient.return_value.query_invoice_by_doc_number.assert_not_called()
        MockClient.return_value.create_invoice.assert_called_once()
        assert synced_invoice.external_invoice_id == "QBO_NEW_001"

    def test_retry_with_existing_qbo_invoice_links_without_recreating(
        self, db, synced_invoice, company, invoice_item
    ):
        """attempts=1 + QBO already has the invoice → link, do not create."""
        self._setup(db, synced_invoice, company, invoice_item)
        existing = QBOResult(
            data={
                "QueryResponse": {
                    "Invoice": [
                        {
                            "Id": "QBO_RECONCILED_999",
                            "SyncToken": "0",
                            "DocNumber": "INV-2026-000000100",
                        }
                    ],
                    "totalCount": 1,
                }
            }
        )
        patcher, MockClient = _patch_create_client(QBO_CREATE_RESPONSE, existing)
        try:
            execute_job(_make_job("create", attempts=1), db)
        finally:
            patcher.stop()

        MockClient.return_value.query_invoice_by_doc_number.assert_called_once_with(
            "INV-2026-000000100"
        )
        MockClient.return_value.create_invoice.assert_not_called()
        assert synced_invoice.external_invoice_id == "QBO_RECONCILED_999"
        assert synced_invoice.sync_status == "complete"

    def test_retry_with_no_qbo_match_falls_through_to_create(
        self, db, synced_invoice, company, invoice_item
    ):
        """attempts=1 + QBO has no match → query then create."""
        self._setup(db, synced_invoice, company, invoice_item)
        empty = QBOResult(data={"QueryResponse": {"Invoice": [], "totalCount": 0}})
        patcher, MockClient = _patch_create_client(QBO_CREATE_RESPONSE, empty)
        try:
            execute_job(_make_job("create", attempts=1), db)
        finally:
            patcher.stop()

        MockClient.return_value.query_invoice_by_doc_number.assert_called_once()
        MockClient.return_value.create_invoice.assert_called_once()
        assert synced_invoice.external_invoice_id == "QBO_NEW_001"

    def test_retry_with_existing_match_appends_reconciliation_history(
        self, db, synced_invoice, company, invoice_item
    ):
        """Linking via reconciliation writes an 'outbound_create_reconciled' history row."""
        self._setup(db, synced_invoice, company, invoice_item)
        existing = QBOResult(
            data={
                "QueryResponse": {
                    "Invoice": [
                        {
                            "Id": "QBO_RECONCILED_999",
                            "SyncToken": "0",
                            "DocNumber": "INV-2026-000000100",
                        }
                    ],
                    "totalCount": 1,
                }
            }
        )
        patcher, _ = _patch_create_client(QBO_CREATE_RESPONSE, existing)
        try:
            execute_job(_make_job("create", attempts=1), db)
        finally:
            patcher.stop()

        history = [
            c.args[0]
            for c in db.add.call_args_list
            if isinstance(c.args[0], InvoiceHistory)
        ]
        assert any(h.event_type == "outbound_create_reconciled" for h in history)


# ---------------------------------------------------------------------------
# execute_job — update — conflict detection
# ---------------------------------------------------------------------------


def _http_400_error() -> requests.HTTPError:
    response = MagicMock()
    response.status_code = 400
    err = requests.HTTPError(response=response)
    err.response = response
    return err


class TestExecuteUpdateConflict:
    """
    When QBO rejects an update with HTTP 400 (SyncToken conflict), the executor
    refetches the QBO state and decides:

    - If QBO matches our intended state, the prior write actually landed; we
      refresh the local sync_token and retry once (idempotent).
    - If QBO diverges from intent, a real conflict exists; we flag the invoice
      with sync_status='conflict' and raise ConflictError so the worker can
      mark the job failed without further retries. No silent overwrite.
    """

    def _setup(self, db, invoice, company):
        db.execute.side_effect = [
            make_execute_result(scalar_one=invoice),
            make_execute_result(scalar_one=company),
        ]

    def test_diverging_qbo_state_raises_conflict_and_flags_invoice(
        self, db, synced_invoice, company
    ):
        """QBO 400 → refetch shows different TotalAmt → ConflictError, sync_status=conflict."""
        synced_invoice.total_amount = Decimal("500.00")
        self._setup(db, synced_invoice, company)

        diverging_qbo = QBOResult(
            data={
                "Invoice": {
                    "Id": "QBO_001",
                    "SyncToken": "9",
                    "TotalAmt": 9999.00,
                    "TxnDate": str(synced_invoice.issue_date),
                }
            }
        )

        with patch("app.services.sync_executor.QuickBooksClient") as MockClient:
            MockClient.return_value.update_invoice.side_effect = _http_400_error()
            MockClient.return_value.read_invoice.return_value = diverging_qbo
            MockClient.return_value.invoice_base_url = "http://mock/invoice"
            MockClient.return_value._invoice_base_url = "http://mock/invoice"

            with pytest.raises(ConflictError) as exc:
                execute_job(_make_job("update"), db)

        assert "TotalAmt" in exc.value.divergent_fields
        assert synced_invoice.sync_status == "conflict"
        assert synced_invoice.sync_token == "9"

    def test_matching_qbo_state_refreshes_token_and_retries(
        self, db, synced_invoice, company
    ):
        """QBO 400 → refetch matches intent → retry succeeds, no conflict raised."""
        synced_invoice.total_amount = Decimal("500.00")
        self._setup(db, synced_invoice, company)

        matching_qbo = QBOResult(
            data={
                "Invoice": {
                    "Id": "QBO_001",
                    "SyncToken": "9",
                    "TotalAmt": 500.00,
                    "TxnDate": str(synced_invoice.issue_date),
                    "DueDate": str(synced_invoice.due_date),
                }
            }
        )
        retry_success = QBOResult(
            data={"Invoice": {"Id": "QBO_001", "SyncToken": "10"}},
            request_body={},
        )

        with patch("app.services.sync_executor.QuickBooksClient") as MockClient:
            MockClient.return_value.update_invoice.side_effect = [
                _http_400_error(),
                retry_success,
            ]
            MockClient.return_value.read_invoice.return_value = matching_qbo
            MockClient.return_value.invoice_base_url = "http://mock/invoice"
            MockClient.return_value._invoice_base_url = "http://mock/invoice"

            execute_job(_make_job("update"), db)

        assert synced_invoice.sync_token == "10"
        assert synced_invoice.sync_status == "complete"

    def test_conflict_writes_invoice_history_row(self, db, synced_invoice, company):
        """Conflict path appends a 'conflict_detected' invoice_history entry."""
        synced_invoice.total_amount = Decimal("500.00")
        self._setup(db, synced_invoice, company)

        diverging_qbo = QBOResult(
            data={
                "Invoice": {
                    "Id": "QBO_001",
                    "SyncToken": "9",
                    "TotalAmt": 9999.00,
                    "TxnDate": str(synced_invoice.issue_date),
                }
            }
        )

        with patch("app.services.sync_executor.QuickBooksClient") as MockClient:
            MockClient.return_value.update_invoice.side_effect = _http_400_error()
            MockClient.return_value.read_invoice.return_value = diverging_qbo
            MockClient.return_value.invoice_base_url = "http://mock/invoice"
            MockClient.return_value._invoice_base_url = "http://mock/invoice"

            with pytest.raises(ConflictError):
                execute_job(_make_job("update"), db)

        history = [
            c.args[0]
            for c in db.add.call_args_list
            if isinstance(c.args[0], InvoiceHistory)
        ]
        assert any(h.event_type == "conflict_detected" for h in history)
