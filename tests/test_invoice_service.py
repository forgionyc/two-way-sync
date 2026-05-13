"""
Tests for app/services/invoice_service.py

Covers the ideeas-side of each outbound scenario:
  - create  → SyncJob(operation='create') enqueued, invoice history recorded
  - update  → sync_status reset to 'pending', SyncJob(operation='update') enqueued
  - delete  → soft-delete + SyncJob(operation='delete') enqueued
  - void    → status='Voided' + SyncJob(operation='void') enqueued
  - guard rails: 404 on missing company/customer, 409 on invalid state transitions
"""

import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.models.models import InvoiceItem, SyncJob
from app.services.invoice_service import (
    create_invoice,
    delete_invoice,
    update_invoice,
    void_invoice,
)
from tests.conftest import make_execute_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_create_data(company_id=1, customer_id=20):
    return SimpleNamespace(
        company_id=company_id,
        customer_id=customer_id,
        total_amount=Decimal("500.00"),
        issue_date=datetime.date(2026, 1, 1),
        due_date=datetime.date(2026, 2, 1),
        items=[
            SimpleNamespace(
                model_dump=lambda: {
                    "item_id": "ITEM_001",
                    "description": "Consulting",
                    "quantity": Decimal("1"),
                    "unit_price": Decimal("500.00"),
                    "amount": Decimal("500.00"),
                }
            )
        ],
    )


def _sync_jobs(db):
    return [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], SyncJob)]


# ---------------------------------------------------------------------------
# create_invoice
# ---------------------------------------------------------------------------


class TestCreateInvoice:
    def test_enqueues_create_job(self, db, company, customer):
        """create_invoice always enqueues a SyncJob with operation='create'."""
        db.get.side_effect = lambda model, _id: company if model.__name__ == "Company" else customer

        create_invoice(_make_create_data(), db)

        jobs = _sync_jobs(db)
        assert len(jobs) == 1
        assert jobs[0].operation == "create"
        assert jobs[0].status == "pending"

    def test_invoice_starts_as_draft(self, db, company, customer):
        """create_invoice sets invoice status to 'Draft' before sync."""
        from app.models.models import Invoice

        db.get.side_effect = lambda model, _id: company if model.__name__ == "Company" else customer

        create_invoice(_make_create_data(), db)

        invoices = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], Invoice)]
        assert invoices[0].status == "Draft"

    def test_records_invoice_history(self, db, company, customer):
        """create_invoice records a local_create history entry."""
        from app.models.models import InvoiceHistory

        db.get.side_effect = lambda model, _id: company if model.__name__ == "Company" else customer

        create_invoice(_make_create_data(), db)

        history = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], InvoiceHistory)]
        assert len(history) == 1
        assert history[0].event_type == "local_create"

    def test_creates_invoice_items(self, db, company, customer):
        """create_invoice persists one InvoiceItem per item in the request."""
        db.get.side_effect = lambda model, _id: company if model.__name__ == "Company" else customer

        create_invoice(_make_create_data(), db)

        items = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], InvoiceItem)]
        assert len(items) == 1

    def test_raises_404_if_company_not_found(self, db):
        db.get.return_value = None

        with pytest.raises(HTTPException) as exc:
            create_invoice(_make_create_data(), db)

        assert exc.value.status_code == 404
        assert "Company" in exc.value.detail

    def test_raises_404_if_customer_not_found(self, db, company):
        db.get.side_effect = lambda model, _id: company if model.__name__ == "Company" else None

        with pytest.raises(HTTPException) as exc:
            create_invoice(_make_create_data(), db)

        assert exc.value.status_code == 404
        assert "Customer" in exc.value.detail


# ---------------------------------------------------------------------------
# update_invoice
# ---------------------------------------------------------------------------


class TestUpdateInvoice:
    def _setup_db(self, db, invoice):
        db.execute.return_value = make_execute_result(scalar=invoice)

    def _make_update_data(self, fields=None):
        data = MagicMock()
        data.model_dump.return_value = fields or {"total_amount": Decimal("600.00")}
        return data

    def test_sets_sync_status_pending(self, db, synced_invoice):
        """update_invoice resets sync_status to 'pending' so the worker re-syncs."""
        self._setup_db(db, synced_invoice)

        update_invoice(100, self._make_update_data(), db)

        assert synced_invoice.sync_status == "pending"

    def test_enqueues_update_job(self, db, synced_invoice):
        self._setup_db(db, synced_invoice)

        update_invoice(100, self._make_update_data(), db)

        jobs = _sync_jobs(db)
        assert len(jobs) == 1
        assert jobs[0].operation == "update"

    def test_raises_409_for_voided_invoice(self, db, synced_invoice):
        synced_invoice.status = "Voided"
        self._setup_db(db, synced_invoice)

        with pytest.raises(HTTPException) as exc:
            update_invoice(100, self._make_update_data(), db)

        assert exc.value.status_code == 409

    def test_raises_404_if_invoice_not_found(self, db):
        db.execute.return_value = make_execute_result(scalar=None)

        with pytest.raises(HTTPException) as exc:
            update_invoice(999, self._make_update_data(), db)

        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# delete_invoice
# ---------------------------------------------------------------------------


class TestDeleteInvoice:
    def test_soft_deletes_invoice(self, db, synced_invoice):
        """delete_invoice sets is_deleted=True and status='Deleted'."""
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        delete_invoice(100, db)

        assert synced_invoice.is_deleted is True
        assert synced_invoice.status == "Deleted"

    def test_sets_sync_status_pending(self, db, synced_invoice):
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        delete_invoice(100, db)

        assert synced_invoice.sync_status == "pending"

    def test_enqueues_delete_job(self, db, synced_invoice):
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        delete_invoice(100, db)

        jobs = _sync_jobs(db)
        assert len(jobs) == 1
        assert jobs[0].operation == "delete"


# ---------------------------------------------------------------------------
# void_invoice
# ---------------------------------------------------------------------------


class TestVoidInvoice:
    def test_voids_invoice(self, db, synced_invoice):
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        void_invoice(100, db)

        assert synced_invoice.status == "Voided"

    def test_sets_sync_status_pending(self, db, synced_invoice):
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        void_invoice(100, db)

        assert synced_invoice.sync_status == "pending"

    def test_enqueues_void_job(self, db, synced_invoice):
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        void_invoice(100, db)

        jobs = _sync_jobs(db)
        assert len(jobs) == 1
        assert jobs[0].operation == "void"

    def test_raises_409_if_already_voided(self, db, synced_invoice):
        synced_invoice.status = "Voided"
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        with pytest.raises(HTTPException) as exc:
            void_invoice(100, db)

        assert exc.value.status_code == 409

    def test_raises_409_if_deleted(self, db, synced_invoice):
        synced_invoice.status = "Deleted"
        db.execute.return_value = make_execute_result(scalar=synced_invoice)

        with pytest.raises(HTTPException) as exc:
            void_invoice(100, db)

        assert exc.value.status_code == 409
