from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RunState = Literal["queued", "running", "blocked_for_approval", "succeeded", "failed", "canceled"]


class StartRunRequest(BaseModel):
    plan_id: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    requested_by: str | None = None
    idempotency_key: str | None = None


class ApprovalResolveRequest(BaseModel):
    decision: Literal["approve", "deny"]
    resolved_by: str | None = None


class ApprovalView(BaseModel):
    approval_id: str
    status: Literal["pending", "approved", "denied"]
    prompt: str
    preview: dict[str, Any] | None = None


class ArtifactView(BaseModel):
    artifact_id: str
    kind: str


class ArtifactContentResponse(BaseModel):
    artifact_id: str
    run_id: str
    kind: str
    content_type: str
    metadata: dict[str, Any] | None = None
    payload: Any | None = None
    text: str | None = None


class RunStatusResponse(BaseModel):
    run_id: str
    plan_id: str
    status: RunState
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    current_task_id: str | None = None
    approvals: list[ApprovalView] = Field(default_factory=list)
    artifacts: list[ArtifactView] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# PII profile schemas
# ---------------------------------------------------------------------------


class PIIAddress(BaseModel):
    street: str
    city: str
    state: str
    zip: str = ""
    current: bool = False


class PIIPhone(BaseModel):
    number: str
    type: str = "mobile"


class PIIProfileData(BaseModel):
    full_name: str
    aliases: list[str] = Field(default_factory=list)
    date_of_birth: str | None = None
    addresses: list[PIIAddress] = Field(default_factory=list)
    phone_numbers: list[PIIPhone] = Field(default_factory=list)
    email_addresses: list[str] = Field(default_factory=list)
    relatives: list[str] = Field(default_factory=list)


class CreateProfileRequest(BaseModel):
    label: str = "default"
    profile: PIIProfileData


class ProfileMetadataResponse(BaseModel):
    profile_id: str
    label: str
    data_hash: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Broker status schemas
# ---------------------------------------------------------------------------


class BrokerStatusResponse(BaseModel):
    broker_id: str
    name: str
    category: str
    difficulty: str
    listing_counts: dict[str, int] = Field(default_factory=dict)
    last_scan_at: datetime | None = None
    next_scan_at: datetime | None = None


class BrokerListingResponse(BaseModel):
    listing_id: str
    broker_id: str
    status: str
    listing_url: str | None = None
    confidence: float
    discovered_at: datetime
    removal_sent_at: datetime | None = None
    verified_at: datetime | None = None
    last_checked_at: datetime | None = None
    notes: str | None = None


class HumanQueueItemResponse(BaseModel):
    queue_id: str
    broker_id: str
    action_needed: str
    instructions: str | None = None
    priority: int
    status: str
    created_at: datetime


class CompleteQueueItemRequest(BaseModel):
    notes: str | None = None
