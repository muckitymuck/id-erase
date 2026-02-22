from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from erasure_executor.db.models import RunArtifact


def persist_artifact(
    session: Session,
    artifacts_root: str,
    run_id: str,
    kind: str,
    payload: Any,
    content_type: str = "application/json",
    metadata: dict | None = None,
) -> RunArtifact:
    artifact_id = str(uuid.uuid4())
    run_dir = Path(artifacts_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    if content_type == "application/json":
        path = run_dir / f"{artifact_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        path = run_dir / f"{artifact_id}.txt"
        path.write_text(str(payload), encoding="utf-8")

    art = RunArtifact(
        artifact_id=artifact_id,
        run_id=run_id,
        kind=kind,
        content_type=content_type,
        uri=str(path),
        metadata_json=metadata,
    )
    session.add(art)
    session.commit()
    return art
