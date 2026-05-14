import logging

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.audit import append_invoice_history
from app.core.time import utcnow
from app.models.models import Company, Customer, Invoice, InvoiceItem, SyncJob

logger = logging.getLogger(__name__)


def get_invoice(invoice_id: int, db: Session) -> Invoice:
    invoice = db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.is_deleted == False)  # noqa: E712
    ).scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


def create_invoice(data, db: Session) -> Invoice:
    company = db.get(Company, data.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    customer = db.get(Customer, data.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    invoice = Invoice(
        company_id=data.company_id,
        customer_id=data.customer_id,
        provider_id=company.provider_id,
        status="Draft",
        total_amount=data.total_amount,
        issue_date=data.issue_date,
        due_date=data.due_date,
    )
    db.add(invoice)
    db.flush()

    for item_data in data.items:
        db.add(InvoiceItem(invoice_id=invoice.id, **item_data.model_dump()))

    append_invoice_history(db, invoice, "local_create")
    _enqueue_job(invoice, "create", db)
    db.commit()
    db.refresh(invoice)
    return invoice


def update_invoice(invoice_id: int, data, db: Session) -> Invoice:
    invoice = get_invoice(invoice_id, db)
    if invoice.status == "Voided":
        raise HTTPException(status_code=409, detail="Cannot update a voided invoice")
    update_data = data.model_dump(exclude_unset=True)
    items_data = update_data.pop("items", None)

    for field, value in update_data.items():
        setattr(invoice, field, value)

    if items_data is not None:
        db.execute(delete(InvoiceItem).where(InvoiceItem.invoice_id == invoice_id))
        for item_data in items_data:
            db.add(InvoiceItem(invoice_id=invoice_id, **item_data))

    invoice.sync_status = "pending"
    append_invoice_history(db, invoice, "local_update")
    _enqueue_job(invoice, "update", db)
    db.commit()
    db.refresh(invoice)
    return invoice


def delete_invoice(invoice_id: int, db: Session) -> None:
    invoice = get_invoice(invoice_id, db)
    invoice.is_deleted = True
    invoice.status = "Deleted"
    invoice.sync_status = "pending"
    append_invoice_history(db, invoice, "local_delete")
    _enqueue_job(invoice, "delete", db)
    db.commit()


def void_invoice(invoice_id: int, db: Session) -> Invoice:
    invoice = get_invoice(invoice_id, db)
    if invoice.status == "Voided":
        raise HTTPException(status_code=409, detail="Invoice is already voided")
    if invoice.status == "Deleted":
        raise HTTPException(status_code=409, detail="Cannot void a deleted invoice")
    invoice.status = "Voided"
    invoice.sync_status = "pending"
    append_invoice_history(db, invoice, "local_void")
    _enqueue_job(invoice, "void", db)
    db.commit()
    db.refresh(invoice)
    return invoice


def _enqueue_job(invoice: Invoice, operation: str, db: Session) -> SyncJob:
    job = SyncJob(
        invoice_id=invoice.id,
        company_id=invoice.company_id,
        operation=operation,
        status="pending",
        scheduled_at=utcnow(),
    )
    db.add(job)
    return job
