"""Dead letter tracking for consecutive plan failures.

After N consecutive failures for a broker, disables the scan schedule
and logs an alert.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONSECUTIVE_FAILURES = 3


class DeadLetterTracker:
    """Tracks consecutive plan failures per broker and disables schedules when threshold hit."""

    def __init__(
        self,
        session_factory: Callable,
        max_failures: int = DEFAULT_MAX_CONSECUTIVE_FAILURES,
    ):
        self._session_factory = session_factory
        self._max_failures = max_failures
        # broker_id -> consecutive failure count
        self._failure_counts: dict[str, int] = {}

    def record_success(self, broker_id: str) -> None:
        """Reset failure count on success."""
        self._failure_counts.pop(broker_id, None)

    def record_failure(self, broker_id: str, run_id: str, error: str | None = None) -> bool:
        """Record a failure. Returns True if broker was disabled (dead-lettered)."""
        count = self._failure_counts.get(broker_id, 0) + 1
        self._failure_counts[broker_id] = count

        logger.warning(
            "dead_letter.failure broker=%s count=%d/%d run=%s error=%s",
            broker_id, count, self._max_failures, run_id, (error or "")[:200],
        )

        if count >= self._max_failures:
            self._disable_broker(broker_id)
            return True
        return False

    def _disable_broker(self, broker_id: str) -> None:
        """Disable all scan schedules for a broker."""
        from erasure_executor.db.models import ScanSchedule

        try:
            with self._session_factory() as session:
                schedules = (
                    session.query(ScanSchedule)
                    .filter(ScanSchedule.broker_id == broker_id, ScanSchedule.enabled == True)
                    .all()
                )
                disabled_count = 0
                for schedule in schedules:
                    schedule.enabled = False
                    session.add(schedule)
                    disabled_count += 1
                session.commit()

                logger.error(
                    "dead_letter.broker_disabled broker=%s disabled_schedules=%d "
                    "reason=exceeded %d consecutive failures",
                    broker_id, disabled_count, self._max_failures,
                )
        except Exception:
            logger.exception("dead_letter.disable_failed broker=%s", broker_id)

    def get_failure_count(self, broker_id: str) -> int:
        """Return current consecutive failure count for a broker."""
        return self._failure_counts.get(broker_id, 0)

    def get_dead_lettered(self) -> list[str]:
        """Return list of broker IDs that have been dead-lettered."""
        return [
            bid for bid, count in self._failure_counts.items()
            if count >= self._max_failures
        ]
