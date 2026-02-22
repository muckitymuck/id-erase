from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
import yaml

from erasure_executor.schemas.plan import ErasurePlan


def load_plan(plans_root: str, plan_id: str) -> ErasurePlan:
    root = Path(plans_root)

    # Check direct file first, then brokers/ subdirectory
    candidates = [
        root / f"{plan_id}.yaml",
        root / f"{plan_id}.yml",
        root / "brokers" / f"{plan_id}.yaml",
        root / "brokers" / f"{plan_id}.yml",
    ]
    # Also handle plan_ids like "broker_spokeo" -> "brokers/spokeo.yaml"
    if plan_id.startswith("broker_"):
        short_id = plan_id[7:]  # strip "broker_" prefix
        candidates.extend([
            root / "brokers" / f"{short_id}.yaml",
            root / "brokers" / f"{short_id}.yml",
        ])

    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        raise FileNotFoundError(f"Plan not found for plan_id={plan_id} in {plans_root}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid plan file: {path}")
    return ErasurePlan.model_validate(raw)


def hash_plan(plan: ErasurePlan) -> str:
    packed = json.dumps(plan.model_dump(), sort_keys=True).encode("utf-8")
    return hashlib.sha256(packed).hexdigest()


def validate_params(plan: ErasurePlan, params: dict) -> None:
    if plan.params_schema:
        jsonschema.validate(instance=params, schema=plan.params_schema)
