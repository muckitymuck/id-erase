"""Tests for dead letter tracking."""

from erasure_executor.engine.dead_letter import DeadLetterTracker


class FakeSchedule:
    def __init__(self, schedule_id, broker_id, enabled=True):
        self.schedule_id = schedule_id
        self.broker_id = broker_id
        self.enabled = enabled
        self.__tablename__ = "scan_schedule"


class FakeSession:
    def __init__(self, schedules=None):
        self._schedules = schedules or []
        self._committed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def query(self, model):
        return self

    def filter(self, *args):
        return self

    def all(self):
        return [s for s in self._schedules if s.enabled]

    def add(self, obj):
        pass

    def commit(self):
        self._committed = True


def test_record_success_resets_count():
    tracker = DeadLetterTracker(session_factory=lambda: FakeSession(), max_failures=3)
    tracker._failure_counts["spokeo"] = 2
    tracker.record_success("spokeo")
    assert tracker.get_failure_count("spokeo") == 0


def test_record_failure_increments():
    tracker = DeadLetterTracker(session_factory=lambda: FakeSession(), max_failures=3)
    tracker.record_failure("spokeo", "run-1")
    assert tracker.get_failure_count("spokeo") == 1
    tracker.record_failure("spokeo", "run-2")
    assert tracker.get_failure_count("spokeo") == 2


def test_dead_letter_disables_on_threshold():
    schedules = [FakeSchedule("s1", "spokeo")]
    session = FakeSession(schedules)
    tracker = DeadLetterTracker(session_factory=lambda: session, max_failures=3)

    tracker.record_failure("spokeo", "run-1")
    tracker.record_failure("spokeo", "run-2")
    disabled = tracker.record_failure("spokeo", "run-3", error="timeout")

    assert disabled is True
    assert schedules[0].enabled is False


def test_dead_letter_does_not_disable_below_threshold():
    schedules = [FakeSchedule("s1", "spokeo")]
    session = FakeSession(schedules)
    tracker = DeadLetterTracker(session_factory=lambda: session, max_failures=3)

    disabled = tracker.record_failure("spokeo", "run-1")
    assert disabled is False
    assert schedules[0].enabled is True


def test_get_dead_lettered():
    tracker = DeadLetterTracker(session_factory=lambda: FakeSession(), max_failures=2)
    tracker.record_failure("spokeo", "run-1")
    tracker.record_failure("spokeo", "run-2")

    dead = tracker.get_dead_lettered()
    assert "spokeo" in dead


def test_separate_brokers():
    tracker = DeadLetterTracker(session_factory=lambda: FakeSession(), max_failures=2)
    tracker.record_failure("spokeo", "run-1")
    tracker.record_failure("beenverified", "run-1")

    assert tracker.get_failure_count("spokeo") == 1
    assert tracker.get_failure_count("beenverified") == 1
    assert len(tracker.get_dead_lettered()) == 0
