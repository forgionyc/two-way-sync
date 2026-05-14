import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import append_api_log
from app.db.session import get_db
from app.models.models import Company, WebhookEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_KNOWN_OPERATIONS = frozenset({"created", "updated", "deleted", "voided"})


@router.post("/quickbooks")
async def quickbooks_webhook(request: Request, db: Session = Depends(get_db)):
    events = await request.json()
    for event in events:
        _ingest_event(event, db)

    return {"received": True}


def _ingest_event(event: dict, db: Session) -> None:
    realm_id = event.get("intuitaccountid")
    qbo_invoice_id = event.get("intuitentityid")
    event_type = event.get("type", "")
    cloudevent_id = event.get("id") or None

    if not realm_id or not qbo_invoice_id:
        logger.warning("Webhook event missing required fields: %s", event)
        return

    company = db.execute(
        select(Company).where(Company.external_id == realm_id)
    ).scalar_one_or_none()
    if not company:
        logger.warning("Webhook: unknown realmId=%s", realm_id)
        return

    operation = _extract_operation(event_type)
    if not operation:
        logger.warning("Webhook: unrecognized event type=%s", event_type)
        return

    if cloudevent_id:
        existing = db.execute(
            select(WebhookEvent).where(WebhookEvent.cloudevent_id == cloudevent_id)
        ).scalar_one_or_none()
        if existing:
            logger.info(
                "Webhook: duplicate cloudevent_id=%s, skipping",
                cloudevent_id,
            )
            return

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
    try:
        db.commit()
    except IntegrityError as e:
        # Concurrent identical webhook delivery: the pre-check above is not
        # transactional, so two requests with the same cloudevent_id can both
        # pass it. The UNIQUE constraint on webhook_events.cloudevent_id is the
        # authoritative guard. Treat the loser of the race as a duplicate, not
        # a server error.
        db.rollback()
        if cloudevent_id and "cloudevent_id" in str(e.orig):
            logger.info(
                "Webhook: dedup race on cloudevent_id=%s; treating as duplicate",
                cloudevent_id,
            )
            return
        raise


def _extract_operation(event_type: str) -> str | None:
    parts = event_type.split(".")
    return next((p for p in parts if p in _KNOWN_OPERATIONS), None)
