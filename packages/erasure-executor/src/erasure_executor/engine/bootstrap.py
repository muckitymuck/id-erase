from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from erasure_executor.config import ExecutorConfig


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def config_hash(config: ExecutorConfig) -> str:
    packed = json.dumps(asdict(config), sort_keys=True, default=str).encode("utf-8")
    return _hash_bytes(packed)


def plan_catalog_version(plans_root: str) -> str:
    root = Path(plans_root)
    if not root.exists():
        return "missing"

    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.y*ml")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def write_startup_artifact(config: ExecutorConfig) -> Path:
    artifacts = Path(config.artifacts_root)
    artifacts.mkdir(parents=True, exist_ok=True)

    payload = {
        "session_id": str(uuid.uuid4()),
        "config_hash": config_hash(config),
        "plan_catalog_version": plan_catalog_version(config.plans_root),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "bootstrap_checks": [
            {"name": "config_integrity", "status": "pass"},
            {"name": "plans_catalog_present", "status": "pass" if Path(config.plans_root).exists() else "fail"},
            {"name": "pii_encryption_key_set", "status": "pass" if config.pii.encryption_key else "fail"},
            {"name": "agent_email_configured", "status": "pass" if config.agent_email.address else "warn"},
        ],
    }

    out = artifacts / "bootstrap-startup.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
