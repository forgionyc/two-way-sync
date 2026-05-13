import logging
import random
from decimal import ROUND_HALF_UP, Decimal
from datetime import timedelta

from faker import Faker

from app.db.session import SessionLocal
from app.models.models import Company, Customer, Invoice, InvoiceItem, Provider, User

logger = logging.getLogger(__name__)
fake = Faker()

STATUSES = ["Draft", "Open", "Voided", "Deleted"]
PROVIDERS = [
    {"provider_name": "QuickBooks", "url": "https://quickbooks.api.intuit.com"},
    {"provider_name": "Xero", "url": "https://api.xero.com"},
]


def seed():
    db = SessionLocal()
    try:
        providers = []
        for p in PROVIDERS:
            provider = Provider(**p)
            db.add(provider)
            providers.append(provider)
        db.flush()

        quickbooks = providers[0]

        users = []
        for _ in range(2):
            user = User(
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                email=fake.unique.email(),
                password=fake.password(),
            )
            db.add(user)
            users.append(user)
        db.flush()

        companies = []
        for user in users:
            company = Company(
                external_id=str(fake.random_number(digits=10)),
                user_id=user.id,
                provider_id=quickbooks.id,
                access_token=fake.sha256(),
                refresh_token=fake.sha256(),
            )
            db.add(company)
            companies.append(company)
        db.flush()

        for user, company in zip(users, companies):
            user.company_id = company.id
        db.flush()

        customers = []
        for company in companies:
            customer = Customer(
                company_id=company.id,
                name=fake.name(),
                email=fake.email(),
                phone=fake.phone_number(),
                address=fake.address().replace("\n", ", "),
            )
            db.add(customer)
            customers.append(customer)
        db.flush()

        for i in range(10):
            customer = customers[i % len(customers)]
            issue_date = fake.date_between(start_date="-1y", end_date="today")
            due_date = issue_date + timedelta(days=random.choice([15, 30, 45, 60]))

            invoice = Invoice(
                company_id=customer.company_id,
                customer_id=customer.id,
                provider_id=quickbooks.id,
                external_invoice_id=str(fake.random_number(digits=6)),
                status=random.choice(STATUSES),
                total_amount=Decimal("0"),
                issue_date=issue_date,
                due_date=due_date,
            )
            db.add(invoice)
            db.flush()

            total = Decimal("0")
            for _ in range(random.randint(1, 3)):
                qty = Decimal(str(round(random.uniform(1, 10), 2)))
                unit_price = Decimal(str(round(random.uniform(10, 500), 2)))
                amount = (qty * unit_price).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                total += amount
                db.add(
                    InvoiceItem(
                        invoice_id=invoice.id,
                        item_id=str(fake.random_number(digits=5)),
                        description=fake.bs(),
                        quantity=qty,
                        unit_price=unit_price,
                        amount=amount,
                    )
                )

            invoice.total_amount = total

        db.commit()
        logger.info(
            "Seeded: 2 providers, 2 users, 2 companies, 2 customers, 10 invoices"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
