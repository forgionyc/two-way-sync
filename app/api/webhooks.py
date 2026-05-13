import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import append_api_log
from app.db.session import get_db
from app.models.models import Company, WebhookEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/quickbooks")
async def quickbooks_webhook(request: Request, db: Session = Depends(get_db)):
    events = await request.json()
    for event in events:
        realm_id = event.get("intuitaccountid")
        qbo_invoice_id = event.get("intuitentityid")
        event_type = event.get("type", "")
        cloudevent_id = event.get("id") or None

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

        if cloudevent_id:
            existing = db.execute(
                select(WebhookEvent).where(WebhookEvent.cloudevent_id == cloudevent_id)
            ).scalar_one_or_none()
            if existing:
                logger.info("Webhook: duplicate cloudevent_id=%s, skipping", cloudevent_id)
                continue

        append_api_log(db, "inbound", "POST", "/webhooks/quickbooks", event, 200, None)
        db.add(
            WebhookEvent(
                cloudevent_id=cloudevent_id,
                company_id=company.id,
                external_invoice_id=qbo_invoice_id,
                operation=operation,
                status="pending",
            )
        )
        db.commit()

    return {"received": True}
