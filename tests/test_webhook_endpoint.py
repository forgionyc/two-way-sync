"""
Tests for app/api/webhooks.py  (POST /webhooks/quickbooks)

Covers the HTTP entry point for all inbound QBO events:
  - Valid event → WebhookEvent queued + ApiLog saved → {"received": True}
  - Unknown realmId → event ignored (no WebhookEvent)
  - Duplicate cloudevent_id → event deduplicated (no second WebhookEvent)
  - Missing required fields (no realmId / no invoiceId) → skipped silently
  - Unrecognised event type → skipped silently
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.webhooks import router
from app.db.session import get_db
from app.models.models import ApiLog, WebhookEvent
from tests.conftest import make_execute_result


# ---------------------------------------------------------------------------
# Test app + client fixtures (no lifespan — avoids sync_worker DB connection)
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    _app = FastAPI()
    _app.include_router(router)
    return _app


@pytest.fixture
def client(app, db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _added_of(db, model_class) -> list:
    return [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], model_class)]


def _valid_event(
    realm_id="REALM_001",
    invoice_id="QBO_001",
    event_type="Invoice.created",
    cloudevent_id="EVT_001",
):
    return {
        "intuitaccountid": realm_id,
        "intuitentityid": invoice_id,
        "type": event_type,
        "id": cloudevent_id,
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestQuickbooksWebhookHappyPath:
    def _setup_db_for_known_company(self, db, company):
        db.execute.side_effect = [
            make_execute_result(scalar=company),  # company lookup
            make_execute_result(scalar=None),      # duplicate cloudevent check → no duplicate
        ]

    def test_returns_received_true(self, client, db, company):
        self._setup_db_for_known_company(db, company)

        resp = client.post("/webhooks/quickbooks", json=[_valid_event()])

        assert resp.status_code == 200
        assert resp.json() == {"received": True}

    def test_queues_webhook_event(self, client, db, company):
        """A valid inbound event is persisted as a pending WebhookEvent."""
        self._setup_db_for_known_company(db, company)

        client.post("/webhooks/quickbooks", json=[_valid_event()])

        events = _added_of(db, WebhookEvent)
        assert len(events) == 1
        assert events[0].operation == "created"
        assert events[0].external_invoice_id == "QBO_001"
        assert events[0].status == "pending"
        assert events[0].company_id == company.id

    def test_saves_api_log(self, client, db, company):
        """Every accepted event is logged in api_logs as an inbound POST."""
        self._setup_db_for_known_company(db, company)

        client.post("/webhooks/quickbooks", json=[_valid_event()])

        logs = _added_of(db, ApiLog)
        assert len(logs) == 1

    def test_queues_correct_operation_for_each_event_type(self, client, db, company):
        """The operation is derived from the dot-separated event type string."""
        for event_type, expected_op in [
            ("Invoice.created", "created"),
            ("Invoice.updated", "updated"),
            ("Invoice.deleted", "deleted"),
            ("Invoice.voided", "voided"),
        ]:
            db.reset_mock()
            db.execute.side_effect = [
                make_execute_result(scalar=company),
                make_execute_result(scalar=None),
            ]

            client.post("/webhooks/quickbooks", json=[_valid_event(event_type=event_type)])

            events = _added_of(db, WebhookEvent)
            assert events[0].operation == expected_op, f"failed for {event_type}"


# ---------------------------------------------------------------------------
# Edge cases / guard rails
# ---------------------------------------------------------------------------


class TestQuickbooksWebhookEdgeCases:
    def test_ignores_event_with_unknown_realm_id(self, client, db):
        """realmId not in companies table → no WebhookEvent or ApiLog written."""
        db.execute.return_value = make_execute_result(scalar=None)  # company not found

        client.post("/webhooks/quickbooks", json=[_valid_event(realm_id="UNKNOWN_REALM")])

        db.add.assert_not_called()

    def test_deduplicates_cloudevent_id(self, client, db, company):
        """A second event with the same cloudevent_id is silently dropped."""
        existing_event = MagicMock(spec=WebhookEvent)
        db.execute.side_effect = [
            make_execute_result(scalar=company),          # company lookup
            make_execute_result(scalar=existing_event),   # duplicate found
        ]

        client.post("/webhooks/quickbooks", json=[_valid_event()])

        assert len(_added_of(db, WebhookEvent)) == 0

    def test_ignores_event_missing_realm_id(self, client, db):
        """Event without intuitaccountid is skipped."""
        event = {"intuitentityid": "QBO_001", "type": "Invoice.created", "id": "EVT_X"}

        resp = client.post("/webhooks/quickbooks", json=[event])

        assert resp.status_code == 200
        db.add.assert_not_called()

    def test_ignores_event_missing_invoice_id(self, client, db):
        """Event without intuitentityid is skipped."""
        event = {"intuitaccountid": "REALM_001", "type": "Invoice.created", "id": "EVT_X"}

        resp = client.post("/webhooks/quickbooks", json=[event])

        assert resp.status_code == 200
        db.add.assert_not_called()

    def test_ignores_unrecognised_event_type(self, client, db, company):
        """Event type that contains no known operation is skipped."""
        db.execute.return_value = make_execute_result(scalar=company)

        client.post("/webhooks/quickbooks", json=[_valid_event(event_type="Invoice.SomethingElse")])

        assert len(_added_of(db, WebhookEvent)) == 0

    def test_always_returns_200(self, client, db):
        """Endpoint always returns 200 even when all events are skipped."""
        db.execute.return_value = make_execute_result(scalar=None)

        resp = client.post("/webhooks/quickbooks", json=[_valid_event(realm_id="BAD")])

        assert resp.status_code == 200

    def test_processes_multiple_events_in_one_request(self, client, db, company):
        """A batch payload with two events results in two WebhookEvents."""
        db.execute.side_effect = [
            make_execute_result(scalar=company),  # company for event 1
            make_execute_result(scalar=None),      # no duplicate for event 1
            make_execute_result(scalar=company),  # company for event 2
            make_execute_result(scalar=None),      # no duplicate for event 2
        ]
        events = [
            _valid_event(invoice_id="QBO_001", cloudevent_id="EVT_A"),
            _valid_event(invoice_id="QBO_002", cloudevent_id="EVT_B"),
        ]

        client.post("/webhooks/quickbooks", json=events)

        assert len(_added_of(db, WebhookEvent)) == 2
