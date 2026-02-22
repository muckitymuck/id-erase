"""Tests for all broker plan schema validation."""

from pathlib import Path

import pytest
import yaml

from erasure_executor.schemas.plan import ErasurePlan

PLANS_DIR = Path(__file__).parent.parent.parent.parent / "workspace-template" / "plans" / "brokers"

EXPECTED_BROKERS = [
    "spokeo", "beenverified", "intelius", "familytreenow",
    "truepeoplesearch", "fastpeoplesearch", "peoplefinder",
    "whitepages", "radaris", "acxiom",
]


def _load_plan(broker_id: str) -> ErasurePlan:
    path = PLANS_DIR / f"{broker_id}.yaml"
    assert path.exists(), f"Plan file not found: {path}"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ErasurePlan(**raw)


@pytest.mark.parametrize("broker_id", EXPECTED_BROKERS)
def test_plan_loads(broker_id):
    """Each broker plan should parse without errors."""
    plan = _load_plan(broker_id)
    assert plan.plan_id == f"broker_{broker_id}"
    assert plan.version == "1.0.0"


@pytest.mark.parametrize("broker_id", EXPECTED_BROKERS)
def test_plan_has_tasks(broker_id):
    """Each plan should have at least 3 tasks."""
    plan = _load_plan(broker_id)
    assert len(plan.tasks) >= 3


@pytest.mark.parametrize("broker_id", EXPECTED_BROKERS)
def test_plan_has_params_schema(broker_id):
    """Each plan should define a params schema with profile_id."""
    plan = _load_plan(broker_id)
    assert plan.params_schema is not None
    required = plan.params_schema.get("required", [])
    assert "profile_id" in required


@pytest.mark.parametrize("broker_id", EXPECTED_BROKERS)
def test_plan_task_ids_unique(broker_id):
    """All task IDs within a plan should be unique."""
    plan = _load_plan(broker_id)
    ids = [t.id for t in plan.tasks]
    assert len(ids) == len(set(ids)), f"Duplicate task IDs in {broker_id}: {ids}"


@pytest.mark.parametrize("broker_id", EXPECTED_BROKERS)
def test_plan_dependencies_valid(broker_id):
    """All depends_on references should point to tasks that exist in the plan."""
    plan = _load_plan(broker_id)
    task_ids = {t.id for t in plan.tasks}
    for task in plan.tasks:
        for dep in task.depends_on:
            assert dep in task_ids, f"Task '{task.id}' in {broker_id} depends on unknown task '{dep}'"


def test_all_plans_present():
    """Verify all expected broker plans exist."""
    for broker_id in EXPECTED_BROKERS:
        path = PLANS_DIR / f"{broker_id}.yaml"
        assert path.exists(), f"Missing plan: {path}"


def test_plans_with_approval_gates():
    """Broker plans that submit opt-outs should have approval gates."""
    for broker_id in EXPECTED_BROKERS:
        plan = _load_plan(broker_id)
        # Find tasks that submit forms (side effects)
        submit_tasks = [t for t in plan.tasks if t.requires_approval]
        assert len(submit_tasks) >= 1, f"Broker {broker_id} should have at least one approval-gated task"


def test_whitepages_has_human_queue():
    """WhitePages plan should queue phone verification for human."""
    plan = _load_plan("whitepages")
    queue_tasks = [t for t in plan.tasks if t.type == "queue.human_action"]
    assert len(queue_tasks) >= 1, "WhitePages should queue phone verification"
    assert queue_tasks[0].input.get("action_needed") == "phone_verification"


def test_broker_update_status_tasks():
    """Each plan should have at least one broker.update_status task."""
    for broker_id in EXPECTED_BROKERS:
        plan = _load_plan(broker_id)
        status_tasks = [t for t in plan.tasks if t.type == "broker.update_status"]
        assert len(status_tasks) >= 1, f"Broker {broker_id} should have broker.update_status task"
