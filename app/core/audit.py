import logging

from sqlalchemy.orm import Session

from app.models.models import ApiLog, InvoiceHistory

logger = logging.getLogger(__name__)


def append_api_log(
    db: Session,
    direction: str,
    method: str,
    endpoint: str,
    request_body: dict | None,
    response_status: int,
    response_body: dict | None,
) -> None:
    db.add(
        ApiLog(
            direction=direction,
            method=method,
            endpoint=endpoint,
            request_body=request_body,
            response_status=response_status,
            response_body=response_body,
        )
    )
    db.flush()


def append_invoice_history(db: Session, invoice, event_type: str) -> None:
    snapshot = {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "external_invoice_id": invoice.external_invoice_id,
        "status": invoice.status,
        "is_deleted": invoice.is_deleted,
        "total_amount": str(invoice.total_amount),
        "issue_date": str(invoice.issue_date) if invoice.issue_date else None,
        "due_date": str(invoice.due_date) if invoice.due_date else None,
        "sync_token": invoice.sync_token,
        "last_sync_at": (
            invoice.last_sync_at.isoformat() if invoice.last_sync_at else None
        ),
    }
    db.add(
        InvoiceHistory(
            invoice_id=invoice.id,
            event_type=event_type,
            status_state=invoice.status,
            total_amount=invoice.total_amount,
            external_invoice_id=invoice.external_invoice_id,
            invoice_snapshot=snapshot,
        )
    )
    db.flush()
