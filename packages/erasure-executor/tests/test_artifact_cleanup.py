"""Tests for artifact lifecycle cleanup."""

import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from erasure_executor.engine.artifact_cleanup import ArtifactCleanup


class FakeArtifact:
    def __init__(self, kind, uri, age_days):
        self.artifact_id = f"art-{kind}-{age_days}"
        self.kind = kind
        self.uri = uri
        self.created_at = datetime.utcnow() - timedelta(days=age_days)
        self._deleted = False


class FakeSession:
    def __init__(self, artifacts):
        self._artifacts = artifacts
        self._deleted = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def query(self, model):
        return self

    def all(self):
        return self._artifacts

    def delete(self, obj):
        self._deleted.append(obj)

    def commit(self):
        pass


def test_cleanup_deletes_old_html():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a fake file
        html_path = os.path.join(tmpdir, "old.html")
        with open(html_path, "w") as f:
            f.write("<html>old</html>")

        artifacts = [FakeArtifact("html", "old.html", age_days=10)]
        session = FakeSession(artifacts)

        cleanup = ArtifactCleanup(
            session_factory=lambda: session,
            artifacts_root=tmpdir,
            html_retention_days=7,
        )

        result = cleanup.cleanup_once()
        assert result["html"] == 1
        assert result["total_files"] == 1
        assert not os.path.exists(html_path)


def test_cleanup_keeps_recent_html():
    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "recent.html")
        with open(html_path, "w") as f:
            f.write("<html>recent</html>")

        artifacts = [FakeArtifact("html", "recent.html", age_days=3)]
        session = FakeSession(artifacts)

        cleanup = ArtifactCleanup(
            session_factory=lambda: session,
            artifacts_root=tmpdir,
            html_retention_days=7,
        )

        result = cleanup.cleanup_once()
        assert result["html"] == 0
        assert os.path.exists(html_path)


def test_cleanup_deletes_old_screenshots():
    with tempfile.TemporaryDirectory() as tmpdir:
        sc_path = os.path.join(tmpdir, "old_sc.png")
        with open(sc_path, "wb") as f:
            f.write(b"\x89PNG")

        artifacts = [FakeArtifact("screenshot", "old_sc.png", age_days=35)]
        session = FakeSession(artifacts)

        cleanup = ArtifactCleanup(
            session_factory=lambda: session,
            artifacts_root=tmpdir,
            screenshot_retention_days=30,
        )

        result = cleanup.cleanup_once()
        assert result["screenshot"] == 1
        assert not os.path.exists(sc_path)


def test_cleanup_keeps_confirmations_indefinitely():
    artifacts = [FakeArtifact("confirmation", "receipt.pdf", age_days=365)]
    session = FakeSession(artifacts)

    cleanup = ArtifactCleanup(
        session_factory=lambda: session,
        artifacts_root="/tmp",
        confirmation_retention_days=-1,  # Keep forever
    )

    result = cleanup.cleanup_once()
    assert result.get("confirmation", 0) == 0
    assert len(session._deleted) == 0


def test_cleanup_start_stop():
    cleanup = ArtifactCleanup(
        session_factory=MagicMock(),
        artifacts_root="/tmp",
        poll_interval_seconds=1,
    )
    cleanup.start()
    assert cleanup._thread is not None
    assert cleanup._thread.is_alive()
    cleanup.stop()
    assert not cleanup._thread.is_alive() if cleanup._thread else True
