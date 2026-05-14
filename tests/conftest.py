import os

# Must be set before any app import — app.db.session raises at module load without it
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/testdb")

import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


def make_execute_result(*, scalar=None, scalar_one=None, scalars_all=None):
    """Return a mock that mimics db.execute() for the three common access patterns."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    r.scalar_one.return_value = scalar_one
    r.scalars.return_value.all.return_value = (
        scalars_all if scalars_all is not None else []
    )
    return r


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def company():
    from app.models.models import Company

    c = MagicMock(spec=Company)
    c.id = 1
    c.external_id = "REALM_001"
    c.access_token = "bearer-token"
    c.provider_id = 10
    return c


@pytest.fixture
def customer():
    from app.models.models import Customer

    c = MagicMock(spec=Customer)
    c.id = 20
    c.external_id = "CUST_001"
    return c


@pytest.fixture
def synced_invoice():
    """Invoice that was created in ideeas and has already been synced to QBO."""
    from app.models.models import Invoice

    inv = MagicMock(spec=Invoice)
    inv.id = 100
    inv.external_invoice_id = "QBO_001"
    inv.sync_token = "5"
    inv.sync_status = "complete"
    inv.status = "Open"
    inv.is_deleted = False
    inv.invoice_number = "INV-2026-000000100"
    inv.total_amount = Decimal("500.00")
    inv.issue_date = datetime.date(2026, 1, 1)
    inv.due_date = datetime.date(2026, 2, 1)
    inv.last_sync_at = None
    inv.company_id = 1
    inv.customer_id = 20
    return inv


@pytest.fixture
def invoice_item():
    from app.models.models import InvoiceItem

    item = MagicMock(spec=InvoiceItem)
    item.item_id = "ITEM_001"
    item.description = "Consulting"
    item.quantity = Decimal("1")
    item.unit_price = Decimal("500.00")
    item.amount = Decimal("500.00")
    return item


@pytest.fixture
def qbo_invoice_data():
    """Typical QBO read-invoice response payload (SyncToken=6, newer than fixture's 5)."""
    return {
        "Invoice": {
            "Id": "QBO_001",
            "SyncToken": "6",
            "TotalAmt": "750.00",
            "TxnDate": "2026-01-15",
            "DueDate": "2026-02-15",
            "CustomerRef": {"value": "CUST_001"},
            "Line": [
                {
                    "DetailType": "SalesItemLineDetail",
                    "Amount": 750.00,
                    "Description": "Consulting",
                    "SalesItemLineDetail": {
                        "ItemRef": {"value": "ITEM_001"},
                        "Qty": 1.0,
                        "UnitPrice": 750.00,
                    },
                }
            ],
        }
    }
