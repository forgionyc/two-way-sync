"""
Tests for app/services/webhook_handler.py

Covers every inbound (QBO → ideeas) scenario:

  created:
    - Not found locally → fetches from QBO, creates invoice + items, saves api_log + history
    - Already exists (e.g. just synced from ideeas) → skipped entirely, no db writes
    - Customer not found → skipped after api_log

  updated:
    - QBO sync_token > local → updates fields, saves api_log + history
    - QBO sync_token ≤ local (stale / replay of our own outbound) → skipped after api_log

  deleted:
    - Invoice exists, not already deleted → soft-deletes, saves history
    - Already deleted → skipped

  voided:
    - Invoice exists, not already voided → sets status='Voided', saves history
    - Already voided → skipped
"""

from contextlib import contextmanager
from unittest.mock import patch


from app.integrations.quickbooks_client import QBOResult
from app.models.models import ApiLog, Invoice, InvoiceHistory, InvoiceItem
from app.services.webhook_handler import handle_invoice_event
from tests.conftest import make_execute_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _added_of(db, model_class) -> list:
    return [
        c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], model_class)
    ]


@contextmanager
def _patch_qbo_client(qbo_data: dict, base_url: str = "http://mock/invoice"):
    """Patches QuickBooksClient so read_invoice returns the given payload."""
    with patch("app.services.webhook_handler.QuickBooksClient") as MockClient:
        MockClient.return_value.read_invoice.return_value = QBOResult(data=qbo_data)
        MockClient.return_value._invoice_base_url = base_url
        yield MockClient


# ---------------------------------------------------------------------------
# handle created
# ---------------------------------------------------------------------------


class TestHandleCreated:
    def test_creates_invoice_when_not_found_locally(
        self, db, company, customer, qbo_invoice_data
    ):
        """New invoice arrives from QBO → created in the local database."""
        db.execute.side_effect = [
            make_execute_result(scalar=None),  # _lookup_invoice → not found
            make_execute_result(scalar=customer),  # customer lookup
        ]

        with _patch_qbo_client(qbo_invoice_data):
            handle_invoice_event(company, "QBO_001", "created", "EVT_001", db)

        new_invoices = _added_of(db, Invoice)
        assert len(new_invoices) == 1
        assert new_invoices[0].external_invoice_id == "QBO_001"
        assert new_invoices[0].sync_status == "complete"
        assert new_invoices[0].origin == "qbo"

    def test_creates_line_items(self, db, company, customer, qbo_invoice_data):
        """QBO Line items with SalesItemLineDetail are persisted as InvoiceItems."""
        db.execute.side_effect = [
            make_execute_result(scalar=None),
            make_execute_result(scalar=customer),
        ]

        with _patch_qbo_client(qbo_invoice_data):
            handle_invoice_event(company, "QBO_001", "created", "EVT_001", db)

        assert len(_added_of(db, InvoiceItem)) == 1

    def test_saves_api_log(self, db, company, customer, qbo_invoice_data):
        """Inbound create always logs the GET to QBO in api_logs."""
        db.execute.side_effect = [
            make_execute_result(scalar=None),
            make_execute_result(scalar=customer),
        ]

        with _patch_qbo_client(qbo_invoice_data):
            handle_invoice_event(company, "QBO_001", "created", "EVT_001", db)

        assert len(_added_of(db, ApiLog)) == 1

    def test_saves_invoice_history(self, db, company, customer, qbo_invoice_data):
        db.execute.side_effect = [
            make_execute_result(scalar=None),
            make_execute_result(scalar=customer),
        ]

        with _patch_qbo_client(qbo_invoice_data):
            handle_invoice_event(company, "QBO_001", "created", "EVT_001", db)

        history = _added_of(db, InvoiceHistory)
        assert len(history) == 1
        assert history[0].event_type == "inbound_create"

    def test_skips_entirely_when_invoice_already_exists(
        self, db, company, synced_invoice
    ):
        """
        QBO fires a 'created' event for an invoice that ideeas already synced outbound.
        The handler must skip with no db writes — the invoice already exists locally.
        """
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        with patch("app.services.webhook_handler.QuickBooksClient") as MockClient:
            handle_invoice_event(company, "QBO_001", "created", "EVT_001", db)
            MockClient.return_value.read_invoice.assert_not_called()

        db.add.assert_not_called()

    def test_skips_invoice_creation_when_customer_not_found(
        self, db, company, qbo_invoice_data
    ):
        """Customer not in ideeas → api_log written, but no Invoice created."""
        db.execute.side_effect = [
            make_execute_result(scalar=None),  # no invoice
            make_execute_result(scalar=None),  # no customer
        ]

        with _patch_qbo_client(qbo_invoice_data):
            handle_invoice_event(company, "QBO_001", "created", "EVT_001", db)

        assert len(_added_of(db, Invoice)) == 0
        assert len(_added_of(db, ApiLog)) == 1  # api_log still written


# ---------------------------------------------------------------------------
# handle updated
# ---------------------------------------------------------------------------


class TestHandleUpdated:
    def test_updates_fields_when_qbo_token_is_newer(
        self, db, company, synced_invoice, qbo_invoice_data
    ):
        """
        QBO sync_token=6, local sync_token=5 → invoice is updated (fields + sync_token).
        This is the normal QBO→ideeas update flow; also covers the 'QBO fires back after
        ideeas outbound update with a newer token' case.
        """
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        with _patch_qbo_client(qbo_invoice_data):
            handle_invoice_event(company, "QBO_001", "updated", "EVT_002", db)

        assert synced_invoice.sync_token == "6"
        assert synced_invoice.sync_status == "complete"

    def test_saves_api_log_and_history_on_update(
        self, db, company, synced_invoice, qbo_invoice_data
    ):
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        with _patch_qbo_client(qbo_invoice_data):
            handle_invoice_event(company, "QBO_001", "updated", "EVT_002", db)

        assert len(_added_of(db, ApiLog)) == 1
        history = _added_of(db, InvoiceHistory)
        assert len(history) == 1
        assert history[0].event_type == "inbound_update"

    def test_skips_update_when_qbo_token_is_same_or_older(
        self, db, company, synced_invoice, qbo_invoice_data
    ):
        """
        QBO fires back with sync_token=5 (same as local) after our own outbound update.
        The handler must skip the update — this is a stale/replayed event.
        api_log is still written (the GET to QBO happened), but InvoiceHistory is not.
        """
        synced_invoice.sync_token = "6"  # local is already at 6; QBO sends 6 → stale
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        with _patch_qbo_client(qbo_invoice_data):  # qbo_invoice_data has SyncToken="6"
            handle_invoice_event(company, "QBO_001", "updated", "EVT_002", db)

        assert len(_added_of(db, InvoiceHistory)) == 0
        assert len(_added_of(db, ApiLog)) == 1  # api_log is still saved

    def test_skips_when_invoice_not_found(self, db, company):
        """No local invoice with that external_id → warning logged, nothing written."""
        db.execute.return_value = make_execute_result(scalar=None)

        with patch("app.services.webhook_handler.QuickBooksClient") as MockClient:
            handle_invoice_event(company, "QBO_UNKNOWN", "updated", "EVT_003", db)
            MockClient.return_value.read_invoice.assert_not_called()

        db.add.assert_not_called()


# ---------------------------------------------------------------------------
# handle deleted
# ---------------------------------------------------------------------------


class TestHandleDeleted:
    def test_soft_deletes_invoice(self, db, company, synced_invoice):
        """QBO delete event → is_deleted=True, status='Deleted'."""
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        handle_invoice_event(company, "QBO_001", "deleted", "EVT_004", db)

        assert synced_invoice.is_deleted is True
        assert synced_invoice.status == "Deleted"
        assert synced_invoice.sync_status == "complete"

    def test_saves_history_on_delete(self, db, company, synced_invoice):
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        handle_invoice_event(company, "QBO_001", "deleted", "EVT_004", db)

        history = _added_of(db, InvoiceHistory)
        assert len(history) == 1
        assert history[0].event_type == "inbound_delete"

    def test_skips_when_already_deleted(self, db, company, synced_invoice):
        """
        QBO fires a 'deleted' event for an invoice ideeas already deleted outbound.
        The handler skips — idempotent, no extra history entry.
        """
        synced_invoice.is_deleted = True
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        handle_invoice_event(company, "QBO_001", "deleted", "EVT_004", db)

        assert len(_added_of(db, InvoiceHistory)) == 0

    def test_skips_when_invoice_not_found(self, db, company):
        db.execute.return_value = make_execute_result(scalar=None)

        handle_invoice_event(company, "QBO_UNKNOWN", "deleted", "EVT_005", db)

        db.add.assert_not_called()


# ---------------------------------------------------------------------------
# handle voided
# ---------------------------------------------------------------------------


class TestHandleVoided:
    def test_voids_invoice(self, db, company, synced_invoice):
        """QBO void event → status='Voided', sync_status='complete'."""
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        handle_invoice_event(company, "QBO_001", "voided", "EVT_006", db)

        assert synced_invoice.status == "Voided"
        assert synced_invoice.sync_status == "complete"

    def test_saves_history_on_void(self, db, company, synced_invoice):
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        handle_invoice_event(company, "QBO_001", "voided", "EVT_006", db)

        history = _added_of(db, InvoiceHistory)
        assert len(history) == 1
        assert history[0].event_type == "inbound_void"

    def test_skips_when_already_voided(self, db, company, synced_invoice):
        """
        QBO fires a 'voided' event for an invoice ideeas already voided outbound.
        The handler skips — idempotent.
        """
        synced_invoice.status = "Voided"
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        handle_invoice_event(company, "QBO_001", "voided", "EVT_006", db)

        assert len(_added_of(db, InvoiceHistory)) == 0

    def test_skips_when_invoice_not_found(self, db, company):
        db.execute.return_value = make_execute_result(scalar=None)

        handle_invoice_event(company, "QBO_UNKNOWN", "voided", "EVT_007", db)

        db.add.assert_not_called()

    def test_skips_when_invoice_already_deleted(self, db, company, synced_invoice):
        """
        Mirrors the local rule in invoice_service.void_invoice: a deleted invoice
        cannot be voided. Inbound void of a deleted invoice is a no-op.
        """
        synced_invoice.is_deleted = True
        synced_invoice.status = "Deleted"
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        handle_invoice_event(company, "QBO_001", "voided", "EVT_008", db)

        assert synced_invoice.status == "Deleted"
        assert len(_added_of(db, InvoiceHistory)) == 0


# ---------------------------------------------------------------------------
# defensive parsing for non-numeric SyncTokens
# ---------------------------------------------------------------------------


class TestDefensiveSyncToken:
    """
    The QBO API documents SyncToken as a numeric string. The handler must not
    crash if QBO ever returns a non-numeric value: it should log a warning and
    skip the update rather than raising ValueError out of the worker.
    """

    def test_non_numeric_qbo_token_is_skipped_safely(self, db, company, synced_invoice):
        bad_qbo = {
            "Invoice": {
                "Id": "QBO_001",
                "SyncToken": "not-a-number",
                "TotalAmt": "750.00",
                "TxnDate": "2026-01-15",
                "CustomerRef": {"value": "CUST_001"},
                "Line": [],
            }
        }
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        with _patch_qbo_client(bad_qbo):
            handle_invoice_event(company, "QBO_001", "updated", "EVT_BAD", db)

        # No history entry written; no crash propagated.
        assert len(_added_of(db, InvoiceHistory)) == 0
