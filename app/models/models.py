import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import attributes, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    company_id = Column(
        BigInteger, ForeignKey("companies.id", use_alter=True), nullable=True
    )
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    company = relationship("Company", foreign_keys=[company_id])


class Company(Base):
    __tablename__ = "companies"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    external_id = Column(String, nullable=True)
    company_name = Column(String, nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    provider_id = Column(BigInteger, ForeignKey("providers.id"), nullable=True)
    access_token = Column(String, nullable=True)
    refresh_token = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User", foreign_keys=[user_id])
    provider = relationship("Provider")
    customers = relationship("Customer", back_populates="company")
    invoices = relationship("Invoice", back_populates="company")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    company_id = Column(BigInteger, ForeignKey("companies.id"), nullable=False)
    external_id = Column(String, nullable=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    company = relationship("Company", back_populates="customers")
    invoices = relationship("Invoice", back_populates="customer")


class Provider(Base):
    __tablename__ = "providers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    provider_name = Column(String, nullable=False, unique=True)
    url = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    invoices = relationship("Invoice", back_populates="provider")


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(
            "length(invoice_number) >= 18", name="ck_invoice_number_min_length"
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    invoice_number = Column(String, unique=True, nullable=True)
    external_invoice_id = Column(String, nullable=True)
    provider_id = Column(BigInteger, ForeignKey("providers.id"), nullable=True)
    company_id = Column(BigInteger, ForeignKey("companies.id"), nullable=False)
    customer_id = Column(BigInteger, ForeignKey("customers.id"), nullable=False)
    status = Column(String, nullable=False)
    is_deleted = Column(Boolean, server_default="false", nullable=False)
    total_amount = Column(Numeric(10, 2), nullable=False)
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=True)
    origin = Column(String, nullable=False, server_default="local")
    sync_status = Column(String, nullable=False, server_default="pending")
    last_sync_at = Column(DateTime, nullable=True)
    sync_token = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    provider = relationship("Provider", back_populates="invoices")
    company = relationship("Company", back_populates="invoices")
    customer = relationship("Customer", back_populates="invoices")
    items = relationship("InvoiceItem", back_populates="invoice")
    history = relationship("InvoiceHistory", back_populates="invoice")
    sync_jobs = relationship("SyncJob", back_populates="invoice")


@event.listens_for(Invoice, "after_insert")
def generate_invoice_number(mapper, connection, target):
    year = datetime.datetime.now().year
    invoice_number = f"INV-{year}-{target.id:09d}"
    connection.execute(
        Invoice.__table__.update()
        .where(Invoice.__table__.c.id == target.id)
        .values(invoice_number=invoice_number)
    )
    attributes.set_committed_value(target, "invoice_number", invoice_number)


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    invoice_id = Column(BigInteger, ForeignKey("invoices.id"), nullable=False)
    item_id = Column(String, nullable=False)
    description = Column(String, nullable=True)
    quantity = Column(Numeric(10, 4), nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)

    invoice = relationship("Invoice", back_populates="items")


class ApiLog(Base):
    __tablename__ = "api_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    direction = Column(String, nullable=False)
    method = Column(String, nullable=False)
    endpoint = Column(String, nullable=False)
    request_headers = Column(JSONB, nullable=True)
    request_body = Column(JSONB, nullable=True)
    response_status = Column(Integer, nullable=True)
    response_body = Column(JSONB, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class InvoiceHistory(Base):
    __tablename__ = "invoice_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    invoice_id = Column(BigInteger, ForeignKey("invoices.id"), nullable=False)
    event_type = Column(String, nullable=True)
    status_state = Column(String, nullable=True)
    total_amount = Column(Numeric(10, 2), nullable=True)
    external_invoice_id = Column(String, nullable=True)
    invoice_snapshot = Column(JSONB, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    invoice = relationship("Invoice", back_populates="history")


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    invoice_id = Column(BigInteger, ForeignKey("invoices.id"), nullable=False)
    company_id = Column(BigInteger, ForeignKey("companies.id"), nullable=False)
    operation = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    error_message = Column(String, nullable=True)
    scheduled_at = Column(DateTime, nullable=False)
    executed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    invoice = relationship("Invoice", back_populates="sync_jobs")
    company = relationship("Company")


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    cloudevent_id = Column(String, nullable=True, unique=True)
    company_id = Column(BigInteger, ForeignKey("companies.id"), nullable=False)
    external_invoice_id = Column(String, nullable=False)
    operation = Column(String, nullable=False)
    status = Column(String, nullable=False, server_default="pending")
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    error_message = Column(String, nullable=True)
    scheduled_at = Column(DateTime, server_default=func.now(), nullable=False)
    executed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    company = relationship("Company")
