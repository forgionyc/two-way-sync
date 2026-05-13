import logging
from datetime import datetime

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import append_api_log, append_invoice_history
from app.core.config import QUICKBOOKS_BASE_URL
from app.integrations.quickbooks_client import QuickBooksClient
from app.models.models import Company, Invoice, InvoiceItem, SyncJob

logger = logging.getLogger(__name__)


def execute_job(job: SyncJob, db: Session) -> None:
    invoice = db.execute(
        select(Invoice).where(Invoice.id == job.invoice_id)
    ).scalar_one()
    company = db.execute(
        select(Company).where(Company.id == job.company_id)
    ).scalar_one()

    client = QuickBooksClient(
        base_url=QUICKBOOKS_BASE_URL,
        realm_id=company.external_id,
        access_token=company.access_token or "",
    )

    if job.operation == "create":
        _execute_create(client, invoice, db)
    elif job.operation == "update":
        _execute_update(client, invoice, db)
    elif job.operation == "delete":
        _execute_delete(client, invoice, db)
    elif job.operation == "void":
        _execute_void(client, invoice, db)
    else:
        raise ValueError(f"Unknown operation: {job.operation}")


def _execute_create(client: QuickBooksClient, invoice: Invoice, db: Session) -> None:
    if invoice.external_invoice_id:
        logger.warning(
            "Invoice %d already has external_invoice_id=%s, skipping QBO create",
            invoice.id,
            invoice.external_invoice_id,
        )
        return

    items = (
        db.execute(select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id))
        .scalars()
        .all()
    )

    # Load customer for CustomerRef.value
    _ = invoice.customer

    result = client.create_invoice(invoice, items)
    qbo_invoice = result.data["Invoice"]

    invoice.external_invoice_id = qbo_invoice["Id"]
    invoice.sync_token = qbo_invoice["SyncToken"]
    invoice.status = "Synced"
    invoice.last_sync_at = datetime.utcnow()
    db.flush()

    append_api_log(
        db,
        "outbound",
        "POST",
        client._invoice_base_url,
        result.request_body,
        200,
        result.data,
    )
    append_invoice_history(db, invoice, "outbound_create")
    logger.info(
        "Outbound create: invoice %d synced to QBO id=%s",
        invoice.id,
        qbo_invoice["Id"],
    )


def _execute_update(client: QuickBooksClient, invoice: Invoice, db: Session) -> None:
    changed_fields: dict = {
        "TxnDate": str(invoice.issue_date),
        "TotalAmt": float(invoice.total_amount),
    }
    if invoice.due_date:
        changed_fields["DueDate"] = str(invoice.due_date)

    try:
        result = client.update_invoice(invoice, changed_fields)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 400:
            logger.warning(
                "SyncToken conflict for invoice %d, fetching latest from QBO and retrying",
                invoice.id,
            )
            read_result = client.read_invoice(invoice.external_invoice_id)
            invoice.sync_token = read_result.data["Invoice"]["SyncToken"]
            db.flush()
            result = client.update_invoice(invoice, changed_fields)
        else:
            raise

    qbo_invoice = result.data["Invoice"]
    invoice.sync_token = qbo_invoice["SyncToken"]
    invoice.last_sync_at = datetime.utcnow()
    db.flush()

    append_api_log(
        db,
        "outbound",
        "POST",
        client._invoice_base_url,
        result.request_body,
        200,
        result.data,
    )
    append_invoice_history(db, invoice, "outbound_update")
    logger.info(
        "Outbound update: invoice %d sync_token=%s",
        invoice.id,
        qbo_invoice["SyncToken"],
    )


def _execute_delete(client: QuickBooksClient, invoice: Invoice, db: Session) -> None:
    result = client.delete_invoice(invoice)
    append_api_log(
        db,
        "outbound",
        "POST",
        f"{client._invoice_base_url}?operation=delete",
        result.request_body,
        200,
        result.data,
    )
    append_invoice_history(db, invoice, "outbound_delete")
    logger.info("Outbound delete: invoice %d deleted in QBO", invoice.id)


def _execute_void(client: QuickBooksClient, invoice: Invoice, db: Session) -> None:
    result = client.void_invoice(invoice)
    append_api_log(
        db,
        "outbound",
        "POST",
        f"{client._invoice_base_url}?operation=void",
        result.request_body,
        200,
        result.data,
    )
    append_invoice_history(db, invoice, "outbound_void")
    logger.info("Outbound void: invoice %d voided in QBO", invoice.id)
