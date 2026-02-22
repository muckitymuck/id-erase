"""Tests for the scan scheduler."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from erasure_executor.engine.scheduler import ErasureScheduler, ScanJob


class FakeSession:
    """Minimal mock session for testing."""
    def __init__(self):
        self._store = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def query(self, model):
        return FakeQuery(self._store.get(model.__tablename__, []))

    def add(self, obj):
        table = obj.__tablename__
        self._store.setdefault(table, []).append(obj)

    def commit(self):
        pass


class FakeQuery:
    def __init__(self, items):
        self._items = items

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def one_or_none(self):
        return self._items[0] if self._items else None

    def all(self):
        return self._items


def test_scheduler_creation():
    scheduler = ErasureScheduler(
        session_factory=MagicMock(),
        poll_interval_seconds=60,
    )
    assert scheduler._poll_interval == 60


def test_scheduler_start_stop():
    scheduler = ErasureScheduler(
        session_factory=MagicMock(),
        poll_interval_seconds=1,
    )
    scheduler.start()
    assert scheduler._thread is not None
    assert scheduler._thread.is_alive()
    scheduler.stop()
    assert not scheduler._thread.is_alive() if scheduler._thread else True


def test_scheduler_initialize_for_profile():
    """Test that initialize_for_profile creates schedule entries."""
    created = []

    class MockSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def query(self, model):
            return type('Q', (), {
                'filter': lambda *a, **kw: type('Q2', (), {'one_or_none': lambda self: None})(),
            })()

        def add(self, obj):
            created.append(obj)

        def commit(self):
            pass

    scheduler = ErasureScheduler(session_factory=MockSession)

    brokers = [
        {"id": "spokeo", "plan_file": "brokers/spokeo.yaml", "recheck_days": 30},
        {"id": "beenverified", "plan_file": "brokers/beenverified.yaml", "recheck_days": 30},
        {"id": "lexisnexis", "plan_file": None, "recheck_days": 90},  # No plan → skipped
    ]

    ids = scheduler.initialize_for_profile("profile-123", brokers)
    # Should create schedules for spokeo and beenverified, skip lexisnexis
    assert len(ids) == 2


def test_scan_job_dataclass():
    job = ScanJob(
        schedule_id="sched-1",
        broker_id="spokeo",
        profile_id="prof-1",
        scan_type="discovery",
        plan_id="broker_spokeo",
        next_run_at=datetime.utcnow(),
        interval_days=30,
    )
    assert job.broker_id == "spokeo"
    assert job.plan_id == "broker_spokeo"
