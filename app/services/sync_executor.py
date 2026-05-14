import logging

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import append_api_log, append_invoice_history
from app.core.config import QUICKBOOKS_BASE_URL
from app.core.time import utcnow
from app.integrations.quickbooks_client import QuickBooksClient
from app.models.models import Company, Invoice, InvoiceItem, SyncJob
from app.services.exceptions import ConflictError

logger = logging.getLogger(__name__)

# Tolerance for monetary equality checks in QBO state comparisons. QBO rounds
# to 2 decimals; we allow a half-cent slop.
_AMOUNT_EPSILON = 0.005


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
        _execute_create(client, invoice, db, attempts=job.attempts)
    elif job.operation == "update":
        _execute_update(client, invoice, db)
    elif job.operation == "delete":
        _execute_delete(client, invoice, db)
    elif job.operation == "void":
        _execute_void(client, invoice, db)
    else:
        raise ValueError(f"Unknown operation: {job.operation}")


def _execute_create(
    client: QuickBooksClient, invoice: Invoice, db: Session, attempts: int = 0
) -> None:
    if invoice.external_invoice_id:
        logger.info(
            "Outbound create skipped: invoice %d already linked to QBO id=%s",
            invoice.id,
            invoice.external_invoice_id,
        )
        return

    # Reconciliation: on retry attempts, query QBO by DocNumber first. A previous
    # attempt may have succeeded server-side but lost the response in transit
    # (timeout-after-write). Without this lookup, the retry duplicates in QBO.
    if attempts > 0:
        existing = _reconcile_by_doc_number(client, invoice, db)
        if existing is not None:
            logger.info(
                "Outbound create reconciled: invoice %d linked to existing QBO id=%s "
                "(retry attempt %d)",
                invoice.id,
                existing,
                attempts,
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
    invoice.status = "Open"
    invoice.sync_status = "complete"
    invoice.last_sync_at = utcnow()
    db.flush()

    append_api_log(
        db,
        "outbound",
        "POST",
        client.invoice_base_url,
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


def _reconcile_by_doc_number(
    client: QuickBooksClient, invoice: Invoice, db: Session
) -> str | None:
    """Look up an existing QBO invoice by DocNumber and link to it if found.

    Returns the QBO invoice id if a match was found and linked; None otherwise.
    """
    if not invoice.invoice_number:
        return None

    result = client.query_invoice_by_doc_number(invoice.invoice_number)
    append_api_log(db, "outbound", "GET", client.query_url, None, 200, result.data)
    invoices = result.data.get("QueryResponse", {}).get("Invoice", [])
    if not invoices:
        return None

    qbo_invoice = invoices[0]
    invoice.external_invoice_id = qbo_invoice["Id"]
    invoice.sync_token = qbo_invoice["SyncToken"]
    invoice.status = "Open"
    invoice.sync_status = "complete"
    invoice.last_sync_at = utcnow()
    db.flush()
    append_invoice_history(db, invoice, "outbound_create_reconciled")
    return qbo_invoice["Id"]


def _execute_update(client: QuickBooksClient, invoice: Invoice, db: Session) -> None:
    intended: dict = {
        "TxnDate": str(invoice.issue_date),
        "TotalAmt": float(invoice.total_amount),
    }
    if invoice.due_date:
        intended["DueDate"] = str(invoice.due_date)

    try:
        result = client.update_invoice(invoice, intended)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 400:
            result = _handle_update_token_conflict(client, invoice, intended, db)
            if result is None:
                return
        else:
            raise

    qbo_invoice = result.data["Invoice"]
    invoice.sync_token = qbo_invoice["SyncToken"]
    invoice.sync_status = "complete"
    invoice.last_sync_at = utcnow()
    db.flush()

    append_api_log(
        db,
        "outbound",
        "POST",
        client.invoice_base_url,
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


def _handle_update_token_conflict(
    client: QuickBooksClient, invoice: Invoice, intended: dict, db: Session
):
    """Handle a 400 from QBO on update. Refetch QBO state and:

    - if it matches our intended state, the prior write actually landed (or a
      concurrent writer reached the same target): refresh sync_token and retry
      once with the new token (idempotent retry).
    - if it diverges, raise ConflictError. The invoice is flagged
      `sync_status='conflict'` and the worker will not retry.

    Returns the QBOResult of the retry on the matching path; None when raising.
    """
    logger.warning(
        "SyncToken conflict for invoice %d, fetching latest from QBO",
        invoice.id,
    )
    read_result = client.read_invoice(invoice.external_invoice_id)
    append_api_log(
        db,
        "outbound",
        "GET",
        f"{client.invoice_base_url}/{invoice.external_invoice_id}",
        None,
        200,
        read_result.data,
    )
    qbo_state = read_result.data["Invoice"]

    divergent = _diff_against_intent(qbo_state, intended)
    if divergent:
        invoice.sync_token = qbo_state["SyncToken"]
        invoice.sync_status = "conflict"
        append_invoice_history(db, invoice, "conflict_detected")
        db.flush()
        logger.error(
            "Conflict detected on invoice %d: divergent fields=%s. Marked sync_status=conflict.",
            invoice.id,
            divergent,
        )
        raise ConflictError(invoice.id, divergent)

    invoice.sync_token = qbo_state["SyncToken"]
    db.flush()
    return client.update_invoice(invoice, intended)


def _diff_against_intent(qbo_state: dict, intended: dict) -> list[str]:
    divergent: list[str] = []
    qbo_total = qbo_state.get("TotalAmt", 0) or 0
    if abs(float(qbo_total) - float(intended["TotalAmt"])) > _AMOUNT_EPSILON:
        divergent.append("TotalAmt")
    if qbo_state.get("TxnDate") != intended["TxnDate"]:
        divergent.append("TxnDate")
    if "DueDate" in intended and qbo_state.get("DueDate") != intended["DueDate"]:
        divergent.append("DueDate")
    return divergent


def _execute_delete(client: QuickBooksClient, invoice: Invoice, db: Session) -> None:
    result = client.delete_invoice(invoice)
    invoice.sync_status = "complete"
    db.flush()
    append_api_log(
        db,
        "outbound",
        "POST",
        f"{client.invoice_base_url}?operation=delete",
        result.request_body,
        200,
        result.data,
    )
    append_invoice_history(db, invoice, "outbound_delete")
    logger.info("Outbound delete: invoice %d deleted in QBO", invoice.id)


def _execute_void(client: QuickBooksClient, invoice: Invoice, db: Session) -> None:
    result = client.void_invoice(invoice)
    invoice.sync_status = "complete"
    db.flush()
    append_api_log(
        db,
        "outbound",
        "POST",
        f"{client.invoice_base_url}?operation=void",
        result.request_body,
        200,
        result.data,
    )
    append_invoice_history(db, invoice, "outbound_void")
    logger.info("Outbound void: invoice %d voided in QBO", invoice.id)
