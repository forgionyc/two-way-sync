"""
Tests for app/workers/sync_worker.py

Focus: the worker's exception-handling behaviour for the outbound sync_jobs
queue.

  - Generic exception → attempts incremented, status set back to 'pending',
    scheduled_at advanced by exponential backoff, until max_attempts is
    reached, at which point the job is marked 'failed' and the related
    invoice's sync_status is set to 'failed'.
  - ConflictError    → job is terminal: attempts is forced to max_attempts,
    status set to 'failed', NO retry. The invoice has already been flagged
    by the executor.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.models.models import SyncJob
from app.services.exceptions import ConflictError
from app.workers.sync_worker import _backoff, _run_batch


def test_backoff_grows_exponentially_then_caps():
    assert _backoff(1) == 30
    assert _backoff(2) == 60
    assert _backoff(3) == 120
    assert _backoff(4) == 240
    assert _backoff(5) == 300  # cap
    assert _backoff(6) == 300  # still capped


@pytest.fixture
def fake_job():
    job = MagicMock(spec=SyncJob)
    job.id = 42
    job.invoice_id = 100
    job.company_id = 1
    job.operation = "update"
    job.attempts = 0
    job.max_attempts = 3
    job.status = "pending"
    return job


@pytest.fixture
def patched_session(fake_job):
    """
    Patches SessionLocal so _run_batch operates on a MagicMock session that
    yields a single pending job and returns the same job from db.get.
    """
    db = MagicMock()
    # First execute() returns the batch select (one job); subsequent calls fall
    # through to default MagicMock behavior and aren't asserted on.
    select_result = MagicMock()
    select_result.scalars.return_value.all.return_value = [fake_job]
    db.execute.return_value = select_result
    db.get.return_value = fake_job
    with patch(
        "app.workers.sync_worker.SessionLocal",
        return_value=db,
    ):
        yield db


def test_conflict_error_marks_job_failed_without_retry(patched_session, fake_job):
    """ConflictError is terminal: no attempts++, no reschedule, status='failed'."""
    with patch(
        "app.workers.sync_worker.execute_job",
        side_effect=ConflictError(invoice_id=100, divergent_fields=["TotalAmt"]),
    ):
        _run_batch()

    assert fake_job.status == "failed"
    assert fake_job.attempts == fake_job.max_attempts
    assert "TotalAmt" in (fake_job.error_message or "")


def test_generic_error_increments_attempts_and_reschedules(patched_session, fake_job):
    """A non-conflict failure on first attempt → attempts=1, status back to pending."""
    with patch(
        "app.workers.sync_worker.execute_job",
        side_effect=RuntimeError("transient"),
    ):
        _run_batch()

    assert fake_job.attempts == 1
    assert fake_job.status == "pending"


def test_generic_error_at_max_attempts_marks_job_failed(patched_session, fake_job):
    """Once attempts hits max_attempts, status becomes 'failed' and invoice flagged."""
    fake_job.attempts = 2  # one more failure tips into max_attempts
    invoice = MagicMock()
    patched_session.get.side_effect = lambda model, _id: (
        fake_job if model is SyncJob else invoice
    )

    with patch(
        "app.workers.sync_worker.execute_job",
        side_effect=RuntimeError("permanent"),
    ):
        _run_batch()

    assert fake_job.status == "failed"
    assert invoice.sync_status == "failed"
