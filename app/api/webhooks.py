import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import append_api_log
from app.db.session import get_db
from app.models.models import Company
from app.services.webhook_handler import handle_invoice_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/quickbooks")
async def quickbooks_webhook(request: Request, db: Session = Depends(get_db)):
    events = await request.json()
    for event in events:
        realm_id = event.get("intuitaccountid")
        qbo_invoice_id = event.get("intuitentityid")
        event_type = event.get("type", "")
        cloudevent_id = event.get("id", "")

        if not realm_id or not qbo_invoice_id:
            logger.warning("Webhook event missing required fields: %s", event)
            continue

        company = db.execute(
            select(Company).where(Company.external_id == realm_id)
        ).scalar_one_or_none()
        if not company:
            logger.warning("Webhook: unknown realmId=%s", realm_id)
            continue

        parts = event_type.split(".")
        known = {"created", "updated", "deleted", "voided"}
        operation = next((p for p in parts if p in known), None)
        if not operation:
            logger.warning("Webhook: unrecognized event type=%s", event_type)
            continue
        append_api_log(db, "inbound", "POST", "/webhooks/quickbooks", event, 200, None)
        db.commit()
        handle_invoice_event(company, qbo_invoice_id, operation, cloudevent_id, db)

    return {"received": True}
