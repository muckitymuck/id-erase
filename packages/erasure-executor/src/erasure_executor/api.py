from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from erasure_executor.auth import require_bearer
from erasure_executor.config import ExecutorConfig
from erasure_executor.db.models import (
    BrokerListing,
    HumanActionQueue,
    PIIProfile,
    RemovalAction,
    Run,
    RunApproval,
    RunArtifact,
    RunTask,
    ScanSchedule,
)
from erasure_executor.engine.idempotency import find_run_by_idempotency
from erasure_executor.engine.pii_vault import PIIVault
from erasure_executor.engine.plans import hash_plan, load_plan, validate_params
from erasure_executor.engine.runner import Runner
from erasure_executor.metrics import (
    HUMAN_QUEUE_PENDING,
    LISTINGS_TOTAL,
    REMOVALS_TOTAL,
    RUNS_STARTED,
    SCANS_TOTAL,
)
from erasure_executor.schemas.models import (
    ApprovalResolveRequest,
    ArtifactContentResponse,
    BrokerListingResponse,
    BrokerStatusResponse,
    CompleteQueueItemRequest,
    CreateProfileRequest,
    HumanQueueItemResponse,
    ProfileMetadataResponse,
    RunStatusResponse,
    StartRunRequest,
)

logger = logging.getLogger(__name__)

MAX_ARTIFACT_BYTES = 1_000_000


def safe_artifact_path(uri: str, artifacts_root: str) -> Path:
    root = Path(artifacts_root).resolve()
    resolved = (root / uri).resolve()
    if not resolved.is_relative_to(root):
        raise HTTPException(status_code=403, detail="artifact path not allowed")
    return resolved


def _run_to_response(session: Session, run: Run) -> RunStatusResponse:
    approvals = session.query(RunApproval).filter(RunApproval.run_id == run.run_id).all()
    artifacts = session.query(RunArtifact).filter(RunArtifact.run_id == run.run_id).all()
    running_task = (
        session.query(RunTask)
        .filter(RunTask.run_id == run.run_id, RunTask.status == "running")
        .order_by(RunTask.task_index.asc())
        .first()
    )

    return RunStatusResponse(
        run_id=run.run_id,
        plan_id=run.plan_id,
        status=run.status,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        current_task_id=running_task.task_id if running_task else None,
        approvals=[
            {"approval_id": a.approval_id, "status": a.status, "prompt": a.prompt, "preview": a.preview_json}
            for a in approvals
        ],
        artifacts=[{"artifact_id": art.artifact_id, "kind": art.kind} for art in artifacts],
    )


def _read_artifact_payload(path: Path, content_type: str) -> tuple[Any | None, str | None]:
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact file missing")
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise HTTPException(status_code=413, detail="artifact exceeds size limit")

    text = path.read_text(encoding="utf-8")
    if content_type == "application/json":
        try:
            return json.loads(text), None
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail="artifact json decode failed") from exc
    return None, text


def build_app(
    config: ExecutorConfig,
    session_factory,
    runner: Runner,
    catalog=None,
    scheduler=None,
) -> FastAPI:
    app = FastAPI(title="id-erase Executor", version="0.1.0")

    vault = PIIVault.from_hex(config.pii.encryption_key) if config.pii.encryption_key else None

    @app.on_event("startup")
    def on_startup() -> None:
        runner.start()
        if scheduler and config.scheduler.enabled:
            scheduler.start()

    @app.on_event("shutdown")
    def on_shutdown() -> None:
        runner.stop()
        if scheduler:
            scheduler.stop()

    # -----------------------------------------------------------------------
    # Health & Metrics
    # -----------------------------------------------------------------------

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/metrics")
    def metrics() -> Response:
        # Update gauge metrics
        with session_factory() as session:
            pending = session.query(HumanActionQueue).filter(HumanActionQueue.status == "pending").count()
            HUMAN_QUEUE_PENDING.set(pending)

            # Listing counts by broker and status
            counts = (
                session.query(BrokerListing.broker_id, BrokerListing.status, func.count())
                .group_by(BrokerListing.broker_id, BrokerListing.status)
                .all()
            )
            for broker_id, status, count in counts:
                LISTINGS_TOTAL.labels(broker=broker_id, status=status).set(count)

        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # -----------------------------------------------------------------------
    # Run Management (reused from seo-fetch)
    # -----------------------------------------------------------------------

    @app.post("/v1/runs", response_model=RunStatusResponse, status_code=202)
    def start_run(req: StartRunRequest, authorization: str | None = Header(default=None)) -> RunStatusResponse:
        require_bearer(authorization, config.auth_token)

        if config.policy.require_idempotency_key and not req.idempotency_key:
            raise HTTPException(status_code=400, detail="idempotency_key is required by policy")

        plan = load_plan(config.plans_root, req.plan_id)
        try:
            validate_params(plan, req.params)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"params validation failed: {exc}") from exc

        with session_factory() as session:
            if req.idempotency_key:
                existing = find_run_by_idempotency(session, req.idempotency_key)
                if existing:
                    return _run_to_response(session, existing)

            run = Run(
                run_id=str(uuid.uuid4()),
                plan_id=req.plan_id,
                plan_hash=hash_plan(plan),
                status="queued",
                requested_by=req.requested_by,
                idempotency_key=req.idempotency_key,
                params_json=req.params,
                created_at=datetime.utcnow(),
            )
            session.add(run)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                if req.idempotency_key:
                    existing = find_run_by_idempotency(session, req.idempotency_key)
                    if existing:
                        return _run_to_response(session, existing)
                raise HTTPException(status_code=409, detail="run conflict")

            RUNS_STARTED.labels(plan_id=req.plan_id).inc()
            SCANS_TOTAL.labels(broker=req.plan_id, result="started").inc()
            return _run_to_response(session, run)

    @app.get("/v1/runs/{run_id}", response_model=RunStatusResponse)
    def get_run(run_id: str, authorization: str | None = Header(default=None)) -> RunStatusResponse:
        require_bearer(authorization, config.auth_token)
        with session_factory() as session:
            run = session.query(Run).filter(Run.run_id == run_id).one_or_none()
            if run is None:
                raise HTTPException(status_code=404, detail="run not found")
            return _run_to_response(session, run)

    @app.post("/v1/runs/{run_id}/approvals/{approval_id}", response_model=RunStatusResponse)
    def resolve_approval(
        run_id: str, approval_id: str, body: ApprovalResolveRequest,
        authorization: str | None = Header(default=None),
    ) -> RunStatusResponse:
        require_bearer(authorization, config.auth_token)
        with session_factory() as session:
            run = session.query(Run).filter(Run.run_id == run_id).one_or_none()
            if run is None:
                raise HTTPException(status_code=404, detail="run not found")

            approval = (
                session.query(RunApproval)
                .filter(RunApproval.approval_id == approval_id, RunApproval.run_id == run_id)
                .one_or_none()
            )
            if approval is None:
                raise HTTPException(status_code=404, detail="approval not found")

            if approval.status == "pending":
                approval.status = "approved" if body.decision == "approve" else "denied"
                approval.resolved_at = datetime.utcnow()
                approval.resolved_by = body.resolved_by
                session.add(approval)

                if approval.status == "approved":
                    if run.status == "blocked_for_approval":
                        run.status = "queued"
                else:
                    run.status = "failed"
                    run.error_code = "APPROVAL_DENIED"
                    run.error_message = f"Approval denied: {approval_id}"
                    run.finished_at = datetime.utcnow()

                session.add(run)
                session.commit()

            return _run_to_response(session, run)

    @app.get("/v1/runs/{run_id}/artifacts/{artifact_id}", response_model=ArtifactContentResponse)
    def get_artifact(
        run_id: str, artifact_id: str, authorization: str | None = Header(default=None),
    ) -> ArtifactContentResponse:
        require_bearer(authorization, config.auth_token)
        with session_factory() as session:
            run = session.query(Run).filter(Run.run_id == run_id).one_or_none()
            if run is None:
                raise HTTPException(status_code=404, detail="run not found")

            artifact = (
                session.query(RunArtifact)
                .filter(RunArtifact.artifact_id == artifact_id, RunArtifact.run_id == run_id)
                .one_or_none()
            )
            if artifact is None:
                raise HTTPException(status_code=404, detail="artifact not found")

            path = safe_artifact_path(artifact.uri, config.artifacts_root)
            payload, text = _read_artifact_payload(path, artifact.content_type)
            return ArtifactContentResponse(
                artifact_id=artifact.artifact_id, run_id=artifact.run_id,
                kind=artifact.kind, content_type=artifact.content_type,
                metadata=artifact.metadata_json, payload=payload, text=text,
            )

    # -----------------------------------------------------------------------
    # PII Profile Management
    # -----------------------------------------------------------------------

    @app.post("/v1/profiles", response_model=ProfileMetadataResponse, status_code=201)
    def create_profile(req: CreateProfileRequest, authorization: str | None = Header(default=None)):
        require_bearer(authorization, config.auth_token)
        if vault is None:
            raise HTTPException(status_code=500, detail="PII encryption key not configured")

        profile_data = req.profile.model_dump()
        ct, iv, tag = vault.encrypt(profile_data)
        data_hash = vault.data_hash(profile_data)
        now = datetime.utcnow()

        profile = PIIProfile(
            profile_id=str(uuid.uuid4()),
            label=req.label,
            encrypted_data=ct,
            encryption_iv=iv,
            encryption_tag=tag,
            data_hash=data_hash,
            created_at=now,
            updated_at=now,
        )

        with session_factory() as session:
            session.add(profile)
            session.commit()

            # Initialize scan schedules for the new profile
            if scheduler and catalog:
                try:
                    broker_dicts = [
                        {"id": b.id, "plan_file": b.plan_file, "recheck_days": b.recheck_days}
                        for b in catalog.all()
                    ]
                    scheduler.initialize_for_profile(profile.profile_id, broker_dicts)
                except Exception:
                    logger.exception("Failed to initialize scan schedules for profile %s", profile.profile_id)

            return ProfileMetadataResponse(
                profile_id=profile.profile_id, label=profile.label,
                data_hash=profile.data_hash, created_at=profile.created_at,
                updated_at=profile.updated_at,
            )

    @app.get("/v1/profiles/{profile_id}", response_model=ProfileMetadataResponse)
    def get_profile(profile_id: str, authorization: str | None = Header(default=None)):
        require_bearer(authorization, config.auth_token)
        with session_factory() as session:
            profile = session.query(PIIProfile).filter(PIIProfile.profile_id == profile_id).one_or_none()
            if profile is None:
                raise HTTPException(status_code=404, detail="profile not found")
            return ProfileMetadataResponse(
                profile_id=profile.profile_id, label=profile.label,
                data_hash=profile.data_hash, created_at=profile.created_at,
                updated_at=profile.updated_at,
            )

    @app.delete("/v1/profiles/{profile_id}", status_code=204)
    def delete_profile(profile_id: str, authorization: str | None = Header(default=None)):
        require_bearer(authorization, config.auth_token)
        with session_factory() as session:
            profile = session.query(PIIProfile).filter(PIIProfile.profile_id == profile_id).one_or_none()
            if profile is None:
                raise HTTPException(status_code=404, detail="profile not found")

            # Cascade delete related data
            session.query(ScanSchedule).filter(ScanSchedule.profile_id == profile_id).delete()
            listings = session.query(BrokerListing).filter(BrokerListing.profile_id == profile_id).all()
            for listing in listings:
                session.query(RemovalAction).filter(RemovalAction.listing_id == listing.listing_id).delete()
                session.query(HumanActionQueue).filter(HumanActionQueue.listing_id == listing.listing_id).delete()
            session.query(BrokerListing).filter(BrokerListing.profile_id == profile_id).delete()
            session.delete(profile)
            session.commit()

    # -----------------------------------------------------------------------
    # Broker Status
    # -----------------------------------------------------------------------

    @app.get("/v1/brokers", response_model=list[BrokerStatusResponse])
    def list_brokers(authorization: str | None = Header(default=None)):
        require_bearer(authorization, config.auth_token)
        with session_factory() as session:
            counts = (
                session.query(BrokerListing.broker_id, BrokerListing.status, func.count())
                .group_by(BrokerListing.broker_id, BrokerListing.status)
                .all()
            )
            broker_counts: dict[str, dict[str, int]] = {}
            for broker_id, status, count in counts:
                broker_counts.setdefault(broker_id, {})[status] = count

            # Get scan schedule info
            schedules = session.query(ScanSchedule).all()
            schedule_map: dict[str, dict] = {}
            for s in schedules:
                schedule_map[s.broker_id] = {
                    "last_scan_at": s.last_run_at,
                    "next_scan_at": s.next_run_at,
                }

            # Build results from catalog (if available) + any DB-only brokers
            results = []
            seen: set[str] = set()

            if catalog:
                for entry in catalog.all():
                    seen.add(entry.id)
                    sched = schedule_map.get(entry.id, {})
                    results.append(BrokerStatusResponse(
                        broker_id=entry.id, name=entry.name, category=entry.category,
                        difficulty=entry.difficulty,
                        listing_counts=broker_counts.get(entry.id, {}),
                        last_scan_at=sched.get("last_scan_at"),
                        next_scan_at=sched.get("next_scan_at"),
                    ))

            # Add any brokers in DB not in catalog
            for broker_id, status_counts in broker_counts.items():
                if broker_id not in seen:
                    sched = schedule_map.get(broker_id, {})
                    results.append(BrokerStatusResponse(
                        broker_id=broker_id, name=broker_id, category="unknown",
                        difficulty="unknown", listing_counts=status_counts,
                        last_scan_at=sched.get("last_scan_at"),
                        next_scan_at=sched.get("next_scan_at"),
                    ))

            return results

    @app.get("/v1/brokers/{broker_id}/listings", response_model=list[BrokerListingResponse])
    def list_broker_listings(broker_id: str, authorization: str | None = Header(default=None)):
        require_bearer(authorization, config.auth_token)
        with session_factory() as session:
            listings = session.query(BrokerListing).filter(BrokerListing.broker_id == broker_id).all()
            return [
                BrokerListingResponse(
                    listing_id=l.listing_id, broker_id=l.broker_id, status=l.status,
                    listing_url=l.listing_url, confidence=l.confidence,
                    discovered_at=l.discovered_at, removal_sent_at=l.removal_sent_at,
                    verified_at=l.verified_at, last_checked_at=l.last_checked_at,
                    notes=l.notes,
                )
                for l in listings
            ]

    # -----------------------------------------------------------------------
    # Human Action Queue
    # -----------------------------------------------------------------------

    @app.get("/v1/queue", response_model=list[HumanQueueItemResponse])
    def list_queue(authorization: str | None = Header(default=None)):
        require_bearer(authorization, config.auth_token)
        with session_factory() as session:
            items = (
                session.query(HumanActionQueue)
                .filter(HumanActionQueue.status == "pending")
                .order_by(HumanActionQueue.priority.desc(), HumanActionQueue.created_at.asc())
                .all()
            )
            return [
                HumanQueueItemResponse(
                    queue_id=i.queue_id, broker_id=i.broker_id,
                    action_needed=i.action_needed, instructions=i.instructions,
                    priority=i.priority, status=i.status, created_at=i.created_at,
                )
                for i in items
            ]

    @app.post("/v1/queue/{queue_id}/complete", status_code=204)
    def complete_queue_item(
        queue_id: str, body: CompleteQueueItemRequest,
        authorization: str | None = Header(default=None),
    ):
        require_bearer(authorization, config.auth_token)
        with session_factory() as session:
            item = session.query(HumanActionQueue).filter(HumanActionQueue.queue_id == queue_id).one_or_none()
            if item is None:
                raise HTTPException(status_code=404, detail="queue item not found")
            item.status = "completed"
            item.completed_at = datetime.utcnow()
            item.completed_notes = body.notes
            session.add(item)
            session.commit()

    # -----------------------------------------------------------------------
    # Schedule
    # -----------------------------------------------------------------------

    @app.get("/v1/schedule")
    def list_schedule(authorization: str | None = Header(default=None)):
        require_bearer(authorization, config.auth_token)
        with session_factory() as session:
            schedules = (
                session.query(ScanSchedule)
                .filter(ScanSchedule.enabled == True)
                .order_by(ScanSchedule.next_run_at.asc())
                .all()
            )
            return [
                {
                    "schedule_id": s.schedule_id,
                    "broker_id": s.broker_id,
                    "scan_type": s.scan_type,
                    "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
                    "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
                    "interval_days": s.interval_days,
                    "enabled": s.enabled,
                }
                for s in schedules
            ]

    @app.post("/v1/schedule/{schedule_id}/trigger", status_code=204)
    def trigger_schedule(schedule_id: str, authorization: str | None = Header(default=None)):
        require_bearer(authorization, config.auth_token)
        with session_factory() as session:
            schedule = session.query(ScanSchedule).filter(ScanSchedule.schedule_id == schedule_id).one_or_none()
            if schedule is None:
                raise HTTPException(status_code=404, detail="schedule not found")
            schedule.next_run_at = datetime.utcnow()
            session.add(schedule)
            session.commit()

    # -----------------------------------------------------------------------
    # Plan Health Check (Phase 3)
    # -----------------------------------------------------------------------

    @app.post("/v1/plans/{plan_id}/check")
    def check_plan_health(plan_id: str, authorization: str | None = Header(default=None)):
        """Check plan health by validating it loads and has valid task references.

        Does NOT run the plan — only validates structure and selector plausibility.
        """
        require_bearer(authorization, config.auth_token)
        try:
            plan = load_plan(config.plans_root, plan_id)
        except Exception as exc:
            return {"plan_id": plan_id, "health": "broken", "error": str(exc), "tasks": []}

        task_ids = {t.id for t in plan.tasks}
        issues = []

        for task in plan.tasks:
            for dep in task.depends_on:
                if dep not in task_ids:
                    issues.append({"task": task.id, "issue": f"missing dependency: {dep}"})

        health = "healthy" if not issues else "degraded"
        return {
            "plan_id": plan_id,
            "health": health,
            "task_count": len(plan.tasks),
            "issues": issues,
            "tasks": [
                {"id": t.id, "type": t.type, "requires_approval": t.requires_approval}
                for t in plan.tasks
            ],
        }

    return app
