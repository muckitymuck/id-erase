from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, Index, JSON, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


# ---------------------------------------------------------------------------
# Reused from seo-fetch (core execution models)
# ---------------------------------------------------------------------------


class Run(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    plan_id: Mapped[str] = mapped_column(String, index=True)
    plan_hash: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, index=True)

    requested_by: Mapped[str | None] = mapped_column(String, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String, unique=True, index=True, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    params_json: Mapped[dict] = mapped_column(JSON, default=dict)
    result_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class RunTask(Base):
    __tablename__ = "run_tasks"

    task_run_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    task_id: Mapped[str] = mapped_column(String, index=True)

    task_index: Mapped[int] = mapped_column(Integer)
    task_name: Mapped[str] = mapped_column(String)
    task_type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, index=True)

    attempt: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    idempotent: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    input_json: Mapped[dict] = mapped_column(JSON, default=dict)
    output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class RunApproval(Base):
    __tablename__ = "run_approvals"

    approval_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    task_id: Mapped[str] = mapped_column(String, index=True)

    status: Mapped[str] = mapped_column(String, index=True)
    prompt: Mapped[str] = mapped_column(Text)
    preview_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String, nullable=True)


class RunArtifact(Base):
    __tablename__ = "run_artifacts"

    artifact_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, index=True)

    kind: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String)
    uri: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# New models for id-erase
# ---------------------------------------------------------------------------


class PIIProfile(Base):
    __tablename__ = "pii_profiles"

    profile_id: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(String, default="default")
    encrypted_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_iv: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_tag: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    data_hash: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BrokerListing(Base):
    __tablename__ = "broker_listings"

    listing_id: Mapped[str] = mapped_column(String, primary_key=True)
    broker_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    profile_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, index=True, nullable=False, default="found")

    listing_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    listing_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    matched_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    removal_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recheck_after: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_broker_listings_recheck", "recheck_after"),
    )


class RemovalAction(Base):
    __tablename__ = "removal_actions"

    action_id: Mapped[str] = mapped_column(String, primary_key=True)
    listing_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    action_type: Mapped[str] = mapped_column(String, nullable=False)

    request_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_status: Mapped[str | None] = mapped_column(String, nullable=True)
    confirmation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class HumanActionQueue(Base):
    __tablename__ = "human_action_queue"

    queue_id: Mapped[str] = mapped_column(String, primary_key=True)
    listing_id: Mapped[str | None] = mapped_column(String, nullable=True)
    broker_id: Mapped[str] = mapped_column(String, nullable=False)
    action_needed: Mapped[str] = mapped_column(Text, nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_human_queue_status", "status"),
    )


class ScanSchedule(Base):
    __tablename__ = "scan_schedule"

    schedule_id: Mapped[str] = mapped_column(String, primary_key=True)
    broker_id: Mapped[str] = mapped_column(String, nullable=False)
    profile_id: Mapped[str] = mapped_column(String, nullable=False)
    scan_type: Mapped[str] = mapped_column(String, default="discovery", nullable=False)

    next_run_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    interval_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_scan_schedule_next", "next_run_at"),
    )
