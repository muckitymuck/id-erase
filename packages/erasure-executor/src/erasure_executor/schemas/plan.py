from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

TaskType = Literal[
    "http.request",
    "scrape.static",
    "scrape.rendered",
    "form.submit",
    "email.send",
    "email.check",
    "email.click_verify",
    "match.identity",
    "broker.update_status",
    "queue.human_action",
    "captcha.solve",
    "wait.delay",
    "llm.json",
    "legal.generate_request",
    "discover.search_engine",
]


class PlanTarget(BaseModel):
    target_id: str = Field(min_length=1)
    kind: Literal["website", "api", "email"]
    base_url: str | None = None
    notes: str | None = None


class PlanTask(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1)
    type: TaskType
    depends_on: list[str] = Field(default_factory=list)

    idempotent: bool = True
    max_attempts: int = Field(default=3, ge=1, le=10)
    timeout_ms: int = Field(default=120000, ge=1000, le=3600000)

    requires_approval: bool = False
    approval: dict[str, Any] | None = None

    input: dict[str, Any]
    output: dict[str, Any] | None = None


class ErasurePlan(BaseModel):
    plan_id: str = Field(min_length=1)
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    description: str | None = None
    owner: str | None = None
    labels: list[str] = Field(default_factory=list)
    targets: list[PlanTarget]
    params_schema: dict[str, Any] | None = None
    tasks: list[PlanTask]
