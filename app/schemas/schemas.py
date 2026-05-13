from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class InvoiceItemBase(BaseModel):
    item_id: str
    description: Optional[str] = None
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


class InvoiceItemCreate(InvoiceItemBase):
    pass


class InvoiceItemResponse(InvoiceItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int


class InvoiceBase(BaseModel):
    external_invoice_id: Optional[str] = None
    provider_id: Optional[int] = None
    company_id: int
    customer_id: int
    status: str
    total_amount: Decimal
    issue_date: date
    due_date: Optional[date] = None


class InvoiceCreate(InvoiceBase):
    items: list[InvoiceItemCreate]


class InvoiceUpdate(BaseModel):
    status: Optional[str] = None
    total_amount: Optional[Decimal] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    external_invoice_id: Optional[str] = None
    provider_id: Optional[int] = None


class InvoiceResponse(InvoiceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_number: Optional[str] = None
    last_sync_at: Optional[datetime] = None
    sync_token: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    items: list[InvoiceItemResponse] = []
