import logging

from faker import Faker

from app.db.session import SessionLocal
from app.models.models import Company, Customer, Provider, User

logger = logging.getLogger(__name__)
fake = Faker()

PROVIDERS = [
    {"provider_name": "QuickBooks", "url": "https://quickbooks.api.intuit.com"},
    {"provider_name": "Xero", "url": "https://api.xero.com"},
]
COMPANIES = [
    {"company_name": "Waste Management", "external_id": "111222333"},
    {"company_name": "Republic Services", "external_id": "444555666"},
]
CUSTOMERS = [
    {"name": "Amy's Bird Sanctuary", "external_id": "1"},
    {"name": "Sonnenschein Family Store", "external_id": "24"},
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
        for user, company_data in zip(users, COMPANIES):
            company = Company(
                external_id=company_data["external_id"],
                company_name=company_data["company_name"],
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
        for company, customer_data in zip(companies, CUSTOMERS):
            customer = Customer(
                company_id=company.id,
                external_id=customer_data["external_id"],
                name=customer_data["name"],
                email=fake.email(),
                phone=fake.phone_number(),
                address=fake.address().replace("\n", ", "),
            )
            db.add(customer)
            customers.append(customer)
        db.flush()

        db.commit()
        logger.info("Seeded: 2 providers, 2 users, 2 companies, 2 customers")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
