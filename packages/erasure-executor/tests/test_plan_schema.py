"""Tests for plan schema validation."""

import pytest
from pydantic import ValidationError

from erasure_executor.schemas.plan import ErasurePlan, PlanTask


def test_valid_plan():
    plan = ErasurePlan(
        plan_id="broker_spokeo",
        version="1.0.0",
        targets=[{"target_id": "spokeo", "kind": "website", "base_url": "https://spokeo.com"}],
        tasks=[
            {
                "id": "search",
                "name": "Search Spokeo",
                "type": "scrape.rendered",
                "input": {"url_template": "/search?q=test"},
            }
        ],
    )
    assert plan.plan_id == "broker_spokeo"
    assert len(plan.tasks) == 1
    assert plan.tasks[0].type == "scrape.rendered"


def test_invalid_version():
    with pytest.raises(ValidationError):
        ErasurePlan(
            plan_id="test",
            version="invalid",
            targets=[{"target_id": "t", "kind": "website"}],
            tasks=[{"id": "t1", "name": "task", "type": "http.request", "input": {}}],
        )


def test_invalid_task_type():
    with pytest.raises(ValidationError):
        PlanTask(id="t1", name="task", type="invalid.type", input={})


def test_all_task_types_valid():
    valid_types = [
        "http.request", "scrape.static", "scrape.rendered", "form.submit",
        "email.send", "email.check", "email.click_verify", "match.identity",
        "broker.update_status", "queue.human_action", "wait.delay", "llm.json",
    ]
    for tt in valid_types:
        task = PlanTask(id=f"t_{tt.replace('.', '_')}", name=f"Test {tt}", type=tt, input={})
        assert task.type == tt


def test_task_defaults():
    task = PlanTask(id="t1", name="task", type="http.request", input={"method": "GET"})
    assert task.idempotent is True
    assert task.max_attempts == 3
    assert task.timeout_ms == 120000
    assert task.requires_approval is False
    assert task.depends_on == []


def test_plan_with_params_schema():
    plan = ErasurePlan(
        plan_id="test",
        version="1.0.0",
        targets=[{"target_id": "t", "kind": "website"}],
        params_schema={
            "type": "object",
            "properties": {"full_name": {"type": "string"}},
            "required": ["full_name"],
        },
        tasks=[{"id": "t1", "name": "task", "type": "http.request", "input": {}}],
    )
    assert plan.params_schema is not None
    assert "full_name" in plan.params_schema["properties"]
