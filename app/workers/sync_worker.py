import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from app.core.config import WORKER_POLL_INTERVAL
from app.core.time import utcnow
from app.db.session import SessionLocal
from app.models.models import Company, Invoice, SyncJob, WebhookEvent
from app.services.exceptions import ConflictError
from app.services.sync_executor import execute_job
from app.services.webhook_handler import handle_invoice_event

logger = logging.getLogger(__name__)

_MAX_BATCH = 10


def _backoff(attempts: int) -> int:
    """Exponential backoff: 30s, 60s, 120s, ..., capped at 300s."""
    return min(300, 30 * (2 ** (attempts - 1)))


async def sync_worker() -> None:
    logger.info("Sync worker started (poll_interval=%ds)", WORKER_POLL_INTERVAL)
    while True:
        for batch_fn in (_run_batch, _run_webhook_batch):
            try:
                batch_fn()
            except Exception as e:
                logger.error("Worker batch error: %s", e, exc_info=True)
        await asyncio.sleep(WORKER_POLL_INTERVAL)


def _run_batch() -> None:
    db = SessionLocal()
    try:
        stmt = (
            select(SyncJob)
            .where(
                SyncJob.status == "pending",
                SyncJob.scheduled_at <= utcnow(),
            )
            .limit(_MAX_BATCH)
            .with_for_update(skip_locked=True)
        )
        jobs = db.execute(stmt).scalars().all()

        if not jobs:
            return

        for job in jobs:
            job.status = "in_progress"
        db.commit()

        for job in jobs:
            job_id = job.id
            invoice_id = job.invoice_id
            try:
                execute_job(job, db)
                job.status = "completed"
                job.executed_at = utcnow()
                db.commit()
                logger.info("Job %d (%s) completed", job_id, job.operation)
            except ConflictError as e:
                # Conflict was already flagged on the invoice in the executor.
                # Mark the job as failed without further retries: a human must
                # resolve the conflict before any further sync is attempted.
                db.rollback()
                logger.error("Job %d aborted by conflict: %s", job_id, e, exc_info=True)
                job = db.get(SyncJob, job_id)
                job.attempts = job.max_attempts
                job.status = "failed"
                job.error_message = str(e)[:1000]
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error("Job %d failed: %s", job_id, e, exc_info=True)
                job = db.get(SyncJob, job_id)
                job.attempts += 1
                job.error_message = str(e)[:1000]
                if job.attempts >= job.max_attempts:
                    job.status = "failed"
                    invoice = db.get(Invoice, invoice_id)
                    if invoice:
                        invoice.sync_status = "failed"
                    logger.error(
                        "Job %d permanently failed after %d attempts",
                        job_id,
                        job.attempts,
                    )
                else:
                    job.status = "pending"
                    job.scheduled_at = utcnow() + timedelta(
                        seconds=_backoff(job.attempts)
                    )
                db.commit()
    finally:
        db.close()


def _run_webhook_batch() -> None:
    db = SessionLocal()
    try:
        stmt = (
            select(WebhookEvent)
            .where(
                WebhookEvent.status == "pending",
                WebhookEvent.scheduled_at <= utcnow(),
            )
            .limit(_MAX_BATCH)
            .with_for_update(skip_locked=True)
        )
        events = db.execute(stmt).scalars().all()

        if not events:
            return

        for event in events:
            event.status = "in_progress"
        db.commit()

        for event in events:
            event_id = event.id
            company_id = event.company_id
            company = db.get(Company, company_id)
            try:
                handle_invoice_event(
                    company,
                    event.external_invoice_id,
                    event.operation,
                    event.cloudevent_id or "",
                    db,
                )
                event.status = "completed"
                event.executed_at = utcnow()
                db.commit()
                logger.info("WebhookEvent %d (%s) completed", event_id, event.operation)
            except Exception as e:
                db.rollback()
                logger.error("WebhookEvent %d failed: %s", event_id, e, exc_info=True)
                event = db.get(WebhookEvent, event_id)
                event.attempts += 1
                event.error_message = str(e)[:1000]
                if event.attempts >= event.max_attempts:
                    event.status = "failed"
                    logger.error(
                        "WebhookEvent %d permanently failed after %d attempts",
                        event_id,
                        event.attempts,
                    )
                else:
                    event.status = "pending"
                    event.scheduled_at = utcnow() + timedelta(
                        seconds=_backoff(event.attempts)
                    )
                db.commit()
    finally:
        db.close()
