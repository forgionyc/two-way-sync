from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.schemas import InvoiceCreate, InvoiceResponse, InvoiceUpdate
from app.services import invoice_service

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.post("", response_model=InvoiceResponse, status_code=201)
def create_invoice(data: InvoiceCreate, db: Session = Depends(get_db)):
    return invoice_service.create_invoice(data, db)


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def read_invoice(invoice_id: int, db: Session = Depends(get_db)):
    return invoice_service.get_invoice(invoice_id, db)


@router.put("/{invoice_id}", response_model=InvoiceResponse)
def update_invoice(invoice_id: int, data: InvoiceUpdate, db: Session = Depends(get_db)):
    return invoice_service.update_invoice(invoice_id, data, db)


@router.delete("/{invoice_id}", status_code=204)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice_service.delete_invoice(invoice_id, db)


@router.post("/{invoice_id}/void", response_model=InvoiceResponse)
def void_invoice(invoice_id: int, db: Session = Depends(get_db)):
    return invoice_service.void_invoice(invoice_id, db)
