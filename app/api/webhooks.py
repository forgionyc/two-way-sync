import logging

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/quickbooks")
async def quickbooks_webhook(request: Request):
    events = await request.json()
    for event in events:
        logger.info(
            "[QB Webhook] type=%s entityId=%s accountId=%s time=%s",
            event.get("type"),
            event.get("intuitentityid"),
            event.get("intuitaccountid"),
            event.get("time"),
        )
    return {"received": True}
