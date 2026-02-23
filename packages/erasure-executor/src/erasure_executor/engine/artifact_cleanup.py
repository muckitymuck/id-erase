"""Artifact retention cleanup job.

Deletes old artifacts based on configurable retention periods.
Runs as a background thread, similar to the scheduler.
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Callable

logger = logging.getLogger(__name__)


class ArtifactCleanup:
    """Background job that deletes expired artifacts."""

    def __init__(
        self,
        session_factory: Callable,
        artifacts_root: str,
        html_retention_days: int = 7,
        screenshot_retention_days: int = 30,
        confirmation_retention_days: int = -1,
        poll_interval_seconds: int = 86400,
    ):
        self._session_factory = session_factory
        self._artifacts_root = artifacts_root
        self._html_days = html_retention_days
        self._screenshot_days = screenshot_retention_days
        self._confirmation_days = confirmation_retention_days
        self._poll_interval = poll_interval_seconds
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def cleanup_once(self) -> dict[str, int]:
        """Run a single cleanup pass. Returns counts of deleted artifacts."""
        from erasure_executor.db.models import RunArtifact

        now = datetime.utcnow()
        deleted = {"html": 0, "screenshot": 0, "total_files": 0}

        with self._session_factory() as session:
            artifacts = session.query(RunArtifact).all()

            for artifact in artifacts:
                age_days = (now - artifact.created_at).days
                should_delete = False

                if artifact.kind == "html" and self._html_days >= 0:
                    should_delete = age_days > self._html_days
                elif artifact.kind == "screenshot" and self._screenshot_days >= 0:
                    should_delete = age_days > self._screenshot_days
                elif artifact.kind in ("confirmation", "receipt"):
                    if self._confirmation_days >= 0:
                        should_delete = age_days > self._confirmation_days
                    # else: keep indefinitely (-1)

                if should_delete:
                    # Delete the file from disk
                    file_deleted = self._delete_file(artifact.uri)
                    if file_deleted:
                        deleted["total_files"] += 1

                    # Delete the DB record
                    session.delete(artifact)
                    deleted[artifact.kind] = deleted.get(artifact.kind, 0) + 1

            session.commit()

        if deleted["total_files"] > 0:
            logger.info(
                "artifact_cleanup.completed html=%d screenshot=%d files=%d",
                deleted["html"], deleted["screenshot"], deleted["total_files"],
            )

        return deleted

    def _delete_file(self, uri: str) -> bool:
        """Delete an artifact file from disk. Returns True if deleted."""
        path = os.path.join(self._artifacts_root, uri)
        try:
            if os.path.exists(path):
                os.remove(path)
                return True
        except OSError:
            logger.warning("artifact_cleanup.delete_failed path=%s", path)
        return False

    def _poll_loop(self) -> None:
        """Background loop that runs cleanup periodically."""
        logger.info("artifact_cleanup.started interval=%ds", self._poll_interval)
        while not self._stop_event.is_set():
            try:
                self.cleanup_once()
            except Exception:
                logger.exception("artifact_cleanup.error")
            self._stop_event.wait(self._poll_interval)
        logger.info("artifact_cleanup.stopped")

    def start(self) -> None:
        """Start the cleanup background thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="artifact-cleanup")
        self._thread.start()

    def stop(self) -> None:
        """Stop the cleanup background thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
