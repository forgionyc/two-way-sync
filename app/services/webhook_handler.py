import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import append_api_log, append_invoice_history
from app.core.config import QUICKBOOKS_BASE_URL
from app.core.time import utcnow
from app.integrations.quickbooks_client import QuickBooksClient
from app.models.models import Company, Customer, Invoice, InvoiceItem

logger = logging.getLogger(__name__)


def handle_invoice_event(
    company: Company,
    qbo_invoice_id: str,
    operation: str,
    cloudevent_id: str,
    db: Session,
) -> None:
    handlers = {
        "created": _handle_created,
        "updated": _handle_updated,
        "deleted": _handle_deleted,
        "voided": _handle_voided,
    }
    handler = handlers.get(operation)
    if not handler:
        logger.warning(
            "Unknown webhook operation: %s [cloudevent_id=%s]",
            operation,
            cloudevent_id,
        )
        return
    handler(company, qbo_invoice_id, cloudevent_id, db)


def _get_client(company: Company) -> QuickBooksClient:
    return QuickBooksClient(
        base_url=QUICKBOOKS_BASE_URL,
        realm_id=company.external_id,
        access_token=company.access_token or "",
    )


def _lookup_invoice(qbo_invoice_id: str, db: Session) -> Invoice | None:
    return db.execute(
        select(Invoice).where(Invoice.external_invoice_id == qbo_invoice_id)
    ).scalar_one_or_none()


def _safe_int(value, label: str) -> int | None:
    """Parse a string to int defensively. Returns None on parse failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        logger.warning(
            "Non-numeric %s received from QBO: %r. Treating as unknown.",
            label,
            value,
        )
        return None


def _handle_created(
    company: Company, qbo_invoice_id: str, cloudevent_id: str, db: Session
) -> None:
    existing = _lookup_invoice(qbo_invoice_id, db)
    if existing:
        logger.info(
            "Inbound create skipped: external_invoice_id=%s already exists "
            "(invoice id=%d) [cloudevent_id=%s]",
            qbo_invoice_id,
            existing.id,
            cloudevent_id,
        )
        return

    client = _get_client(company)
    result = client.read_invoice(qbo_invoice_id)
    append_api_log(
        db,
        "inbound",
        "GET",
        client.invoice_base_url + f"/{qbo_invoice_id}",
        None,
        200,
        result.data,
    )
    qbo_inv = result.data["Invoice"]

    customer_ref = qbo_inv["CustomerRef"]["value"]
    customer = db.execute(
        select(Customer).where(
            Customer.company_id == company.id,
            Customer.external_id == customer_ref,
        )
    ).scalar_one_or_none()
    if not customer:
        logger.warning(
            "Inbound create: no customer with external_id=%s for company %d, skipping",
            customer_ref,
            company.id,
        )
        return

    invoice = Invoice(
        company_id=company.id,
        customer_id=customer.id,
        provider_id=company.provider_id,
        external_invoice_id=qbo_invoice_id,
        sync_token=qbo_inv["SyncToken"],
        status="Created",
        origin="qbo",
        sync_status="complete",
        total_amount=Decimal(str(qbo_inv["TotalAmt"])),
        issue_date=qbo_inv.get("TxnDate"),
        due_date=qbo_inv.get("DueDate"),
        last_sync_at=utcnow(),
    )
    db.add(invoice)
    db.flush()

    for line in qbo_inv.get("Line", []):
        if line.get("DetailType") != "SalesItemLineDetail":
            continue
        detail = line["SalesItemLineDetail"]
        db.add(
            InvoiceItem(
                invoice_id=invoice.id,
                item_id=detail["ItemRef"]["value"],
                description=line.get("Description"),
                quantity=Decimal(str(detail.get("Qty", 1))),
                unit_price=Decimal(str(detail.get("UnitPrice", 0))),
                amount=Decimal(str(line["Amount"])),
            )
        )

    append_invoice_history(db, invoice, "inbound_create")
    db.flush()
    logger.info(
        "Inbound create: invoice id=%d created from QBO id=%s",
        invoice.id,
        qbo_invoice_id,
    )


def _handle_updated(
    company: Company, qbo_invoice_id: str, cloudevent_id: str, db: Session
) -> None:
    invoice = _lookup_invoice(qbo_invoice_id, db)
    if not invoice:
        logger.warning(
            "Inbound update: no invoice with external_invoice_id=%s",
            qbo_invoice_id,
        )
        return

    client = _get_client(company)
    result = client.read_invoice(qbo_invoice_id)
    append_api_log(
        db,
        "inbound",
        "GET",
        client.invoice_base_url + f"/{qbo_invoice_id}",
        None,
        200,
        result.data,
    )
    qbo_inv = result.data["Invoice"]
    qbo_token = _safe_int(qbo_inv.get("SyncToken"), "SyncToken")
    local_token = _safe_int(invoice.sync_token, "SyncToken")

    if qbo_token is None:
        logger.warning(
            "Inbound update skipped: QBO returned non-numeric SyncToken for invoice id=%d",
            invoice.id,
        )
        return

    if local_token is not None and qbo_token <= local_token:
        logger.info(
            "Inbound update skipped: invoice id=%d already at SyncToken=%s, "
            "incoming SyncToken=%s is not newer [cloudevent_id=%s]",
            invoice.id,
            invoice.sync_token,
            qbo_inv.get("SyncToken"),
            cloudevent_id,
        )
        return

    invoice.sync_token = str(qbo_token)
    invoice.total_amount = Decimal(str(qbo_inv["TotalAmt"]))
    if qbo_inv.get("TxnDate"):
        invoice.issue_date = qbo_inv["TxnDate"]
    if qbo_inv.get("DueDate"):
        invoice.due_date = qbo_inv["DueDate"]
    invoice.sync_status = "complete"
    invoice.last_sync_at = utcnow()

    append_invoice_history(db, invoice, "inbound_update")
    db.flush()
    logger.info(
        "Inbound update: invoice id=%d updated to SyncToken=%s",
        invoice.id,
        qbo_token,
    )


def _handle_deleted(
    company: Company, qbo_invoice_id: str, cloudevent_id: str, db: Session
) -> None:
    invoice = _lookup_invoice(qbo_invoice_id, db)
    if not invoice:
        logger.warning(
            "Inbound delete: no invoice with external_invoice_id=%s",
            qbo_invoice_id,
        )
        return
    if invoice.is_deleted:
        logger.info(
            "Inbound delete skipped: invoice id=%d already deleted [cloudevent_id=%s]",
            invoice.id,
            cloudevent_id,
        )
        return

    invoice.is_deleted = True
    invoice.status = "Deleted"
    invoice.sync_status = "complete"
    append_invoice_history(db, invoice, "inbound_delete")
    db.flush()
    logger.info("Inbound delete: soft-deleted invoice id=%d", invoice.id)


def _handle_voided(
    company: Company, qbo_invoice_id: str, cloudevent_id: str, db: Session
) -> None:
    invoice = _lookup_invoice(qbo_invoice_id, db)
    if not invoice:
        logger.warning(
            "Inbound void: no invoice with external_invoice_id=%s",
            qbo_invoice_id,
        )
        return
    if invoice.is_deleted:
        # Mirror the local rule in invoice_service.void_invoice: a deleted
        # invoice cannot be voided. Drop the event idempotently.
        logger.info(
            "Inbound void skipped: invoice id=%d is deleted [cloudevent_id=%s]",
            invoice.id,
            cloudevent_id,
        )
        return
    if invoice.status == "Voided":
        logger.info(
            "Inbound void skipped: invoice id=%d already voided [cloudevent_id=%s]",
            invoice.id,
            cloudevent_id,
        )
        return

    invoice.status = "Voided"
    invoice.sync_status = "complete"
    append_invoice_history(db, invoice, "inbound_void")
    db.flush()
    logger.info("Inbound void: voided invoice id=%d", invoice.id)
