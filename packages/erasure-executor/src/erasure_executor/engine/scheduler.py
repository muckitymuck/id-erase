"""Scan scheduler for periodic broker re-checks.

Polls the scan_schedule table for due jobs and creates runs via the internal API.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class ScanJob:
    schedule_id: str
    broker_id: str
    profile_id: str
    scan_type: str
    plan_id: str
    next_run_at: datetime
    interval_days: int


class ErasureScheduler:
    """Background scheduler that triggers broker scans on schedule."""

    def __init__(
        self,
        session_factory: Callable,
        poll_interval_seconds: int = 300,
        create_run_fn: Callable[[str, dict[str, Any]], str | None] | None = None,
    ):
        self._session_factory = session_factory
        self._poll_interval = poll_interval_seconds
        self._create_run_fn = create_run_fn
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def get_due_jobs(self) -> list[ScanJob]:
        """Return scan schedules where next_run_at <= now and enabled."""
        from erasure_executor.db.models import ScanSchedule

        now = datetime.utcnow()
        with self._session_factory() as session:
            rows = (
                session.query(ScanSchedule)
                .filter(ScanSchedule.enabled == True, ScanSchedule.next_run_at <= now)
                .order_by(ScanSchedule.next_run_at.asc())
                .all()
            )
            jobs = []
            for r in rows:
                plan_id = f"broker_{r.broker_id}"
                jobs.append(ScanJob(
                    schedule_id=r.schedule_id,
                    broker_id=r.broker_id,
                    profile_id=r.profile_id,
                    scan_type=r.scan_type,
                    plan_id=plan_id,
                    next_run_at=r.next_run_at,
                    interval_days=r.interval_days,
                ))
            return jobs

    def mark_started(self, schedule_id: str, run_id: str) -> None:
        """Record that a scheduled scan has started and advance next_run_at."""
        from erasure_executor.db.models import ScanSchedule

        now = datetime.utcnow()
        with self._session_factory() as session:
            schedule = (
                session.query(ScanSchedule)
                .filter(ScanSchedule.schedule_id == schedule_id)
                .one_or_none()
            )
            if schedule is None:
                logger.warning("scheduler.mark_started schedule_id=%s not found", schedule_id)
                return
            schedule.last_run_id = run_id
            schedule.last_run_at = now
            schedule.next_run_at = now + timedelta(days=schedule.interval_days)
            session.add(schedule)
            session.commit()
            logger.info(
                "scheduler.mark_started schedule=%s run=%s next=%s",
                schedule_id, run_id, schedule.next_run_at.isoformat(),
            )

    def initialize_for_profile(self, profile_id: str, catalog_brokers: list[dict[str, Any]]) -> list[str]:
        """Create scan schedules for all catalog brokers for a given profile.

        Args:
            profile_id: PII profile ID
            catalog_brokers: List of broker dicts with id, plan_file, recheck_days

        Returns:
            List of created schedule IDs
        """
        from erasure_executor.db.models import ScanSchedule

        now = datetime.utcnow()
        schedule_ids = []

        with self._session_factory() as session:
            for broker in catalog_brokers:
                broker_id = broker["id"]
                plan_file = broker.get("plan_file")
                if not plan_file:
                    continue  # Skip brokers without a plan (e.g., LexisNexis)

                recheck_days = broker.get("recheck_days", 30)

                # Check if schedule already exists
                existing = (
                    session.query(ScanSchedule)
                    .filter(
                        ScanSchedule.broker_id == broker_id,
                        ScanSchedule.profile_id == profile_id,
                    )
                    .one_or_none()
                )
                if existing:
                    continue

                sid = str(uuid.uuid4())
                schedule = ScanSchedule(
                    schedule_id=sid,
                    broker_id=broker_id,
                    profile_id=profile_id,
                    scan_type="discovery",
                    next_run_at=now,  # Run immediately for new profiles
                    interval_days=recheck_days,
                    enabled=True,
                    created_at=now,
                )
                session.add(schedule)
                schedule_ids.append(sid)

            session.commit()
            logger.info("scheduler.initialized profile=%s schedules=%d", profile_id, len(schedule_ids))

        return schedule_ids

    def _poll_loop(self) -> None:
        """Background loop that polls for due jobs."""
        logger.info("scheduler.started poll_interval=%ds", self._poll_interval)
        while not self._stop_event.is_set():
            try:
                jobs = self.get_due_jobs()
                if jobs:
                    logger.info("scheduler.due_jobs count=%d", len(jobs))

                seen_brokers: set[str] = set()
                for job in jobs:
                    # Rate limit: max 1 concurrent run per broker
                    if job.broker_id in seen_brokers:
                        continue
                    seen_brokers.add(job.broker_id)

                    run_id = None
                    if self._create_run_fn:
                        try:
                            run_id = self._create_run_fn(job.plan_id, {
                                "profile_id": job.profile_id,
                                "scan_type": job.scan_type,
                            })
                        except Exception:
                            logger.exception("scheduler.create_run_failed plan=%s", job.plan_id)
                            continue

                    if run_id:
                        self.mark_started(job.schedule_id, run_id)
                    else:
                        # Still advance the schedule to avoid infinite retry
                        self.mark_started(job.schedule_id, f"skipped-{uuid.uuid4()}")

            except Exception:
                logger.exception("scheduler.poll_error")

            self._stop_event.wait(self._poll_interval)

        logger.info("scheduler.stopped")

    def start(self) -> None:
        """Start the scheduler background thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="erasure-scheduler")
        self._thread.start()

    def stop(self) -> None:
        """Stop the scheduler background thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
