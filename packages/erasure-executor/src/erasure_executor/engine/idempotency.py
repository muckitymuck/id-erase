from __future__ import annotations

from sqlalchemy.orm import Session

from erasure_executor.db.models import Run


def find_run_by_idempotency(session: Session, key: str) -> Run | None:
    return session.query(Run).filter(Run.idempotency_key == key).one_or_none()
