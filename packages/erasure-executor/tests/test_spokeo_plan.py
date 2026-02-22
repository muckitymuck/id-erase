"""Tests for the Spokeo broker plan schema validation."""

from pathlib import Path

import yaml
from pydantic import ValidationError

from erasure_executor.schemas.plan import ErasurePlan


SPOKEO_PLAN_PATH = Path(__file__).parent.parent.parent.parent / "workspace-template" / "plans" / "brokers" / "spokeo.yaml"


def test_spokeo_plan_loads():
    """The spokeo.yaml plan should parse without errors."""
    assert SPOKEO_PLAN_PATH.exists(), f"Spokeo plan not found at {SPOKEO_PLAN_PATH}"
    raw = yaml.safe_load(SPOKEO_PLAN_PATH.read_text(encoding="utf-8"))
    plan = ErasurePlan(**raw)
    assert plan.plan_id == "broker_spokeo"
    assert plan.version == "1.0.0"


def test_spokeo_plan_has_required_tasks():
    raw = yaml.safe_load(SPOKEO_PLAN_PATH.read_text(encoding="utf-8"))
    plan = ErasurePlan(**raw)

    task_ids = [t.id for t in plan.tasks]
    assert "search_listing" in task_ids
    assert "match_results" in task_ids
    assert "submit_optout" in task_ids
    assert "check_verification_email" in task_ids
    assert "click_verify_link" in task_ids
    assert "update_final_status" in task_ids


def test_spokeo_plan_approval_gate():
    """The opt-out submission should require approval."""
    raw = yaml.safe_load(SPOKEO_PLAN_PATH.read_text(encoding="utf-8"))
    plan = ErasurePlan(**raw)

    submit_task = next(t for t in plan.tasks if t.id == "submit_optout")
    assert submit_task.requires_approval is True
    assert submit_task.idempotent is False


def test_spokeo_plan_task_dependencies():
    """Tasks should have correct dependency chains."""
    raw = yaml.safe_load(SPOKEO_PLAN_PATH.read_text(encoding="utf-8"))
    plan = ErasurePlan(**raw)

    deps = {t.id: t.depends_on for t in plan.tasks}
    assert deps["search_listing"] == []
    assert "search_listing" in deps["match_results"]
    assert "match_results" in deps["record_found"]
    assert "record_found" in deps["submit_optout"]
    assert "submit_optout" in deps["check_verification_email"]
    assert "check_verification_email" in deps["click_verify_link"]
    assert "click_verify_link" in deps["update_final_status"]


def test_spokeo_plan_params_schema():
    """Plan should define required parameters."""
    raw = yaml.safe_load(SPOKEO_PLAN_PATH.read_text(encoding="utf-8"))
    plan = ErasurePlan(**raw)

    assert plan.params_schema is not None
    required = plan.params_schema.get("required", [])
    assert "full_name" in required
    assert "profile_id" in required
    assert "agent_email" in required


def test_spokeo_plan_task_types():
    """Tasks should use correct task types."""
    raw = yaml.safe_load(SPOKEO_PLAN_PATH.read_text(encoding="utf-8"))
    plan = ErasurePlan(**raw)

    type_map = {t.id: t.type for t in plan.tasks}
    assert type_map["search_listing"] == "scrape.rendered"
    assert type_map["match_results"] == "match.identity"
    assert type_map["record_found"] == "broker.update_status"
    assert type_map["submit_optout"] == "scrape.rendered"
    assert type_map["check_verification_email"] == "email.check"
    assert type_map["click_verify_link"] == "email.click_verify"
    assert type_map["update_final_status"] == "broker.update_status"
