import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.config import WORKER_POLL_INTERVAL
from app.db.session import SessionLocal
from app.models.models import SyncJob
from app.services.sync_executor import execute_job

logger = logging.getLogger(__name__)

_MAX_BATCH = 10


def _backoff(attempts: int) -> int:
    return min(300, 30 * (2 ** (attempts - 1)))


async def sync_worker() -> None:
    logger.info("Sync worker started (poll_interval=%ds)", WORKER_POLL_INTERVAL)
    while True:
        try:
            _run_batch()
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
                SyncJob.scheduled_at <= datetime.utcnow(),
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
            try:
                execute_job(job, db)
                job.status = "completed"
                job.executed_at = datetime.utcnow()
                db.commit()
                logger.info("Job %d (%s) completed", job_id, job.operation)
            except Exception as e:
                db.rollback()
                logger.error("Job %d failed: %s", job_id, e, exc_info=True)
                job = db.get(SyncJob, job_id)
                job.attempts += 1
                job.error_message = str(e)[:1000]
                if job.attempts >= job.max_attempts:
                    job.status = "failed"
                    logger.error(
                        "Job %d permanently failed after %d attempts",
                        job_id,
                        job.attempts,
                    )
                else:
                    job.status = "pending"
                    job.scheduled_at = datetime.utcnow() + timedelta(
                        seconds=_backoff(job.attempts)
                    )
                db.commit()
    finally:
        db.close()
