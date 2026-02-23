from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from erasure_executor.config import ExecutorConfig
from erasure_executor.db.models import Run, RunApproval, RunTask
from erasure_executor.engine.artifacts import persist_artifact
from erasure_executor.engine.plans import hash_plan, load_plan
from erasure_executor.engine.retries import RetryPolicy
from erasure_executor.metrics import APPROVALS_PENDING, RUNS_FINISHED, SCANS_TOTAL, TASK_DURATION
from erasure_executor.tasks.registry import TaskExecutionContext, execute_task

logger = logging.getLogger(__name__)

SIDE_EFFECT_TYPES = {"form.submit", "email.send", "email.click_verify", "broker.update_status"}
HTTP_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class Runner:
    def __init__(self, session_factory, config: ExecutorConfig):
        self._session_factory = session_factory
        self._config = config
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._runner_id = str(uuid.uuid4())

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        logger.info("runner.started runner_id=%s", self._runner_id)
        while not self._stop.is_set():
            try:
                self._process_once()
            except Exception as exc:
                logger.exception("runner.loop_error: %s", exc)
            time.sleep(1)
        logger.info("runner.stopped runner_id=%s", self._runner_id)

    def _claim_next_run(self, session: Session) -> Run | None:
        now = datetime.utcnow()
        lease_until = now + timedelta(seconds=max(30, self._config.run_claim_ttl_seconds))

        candidates = (
            session.query(Run)
            .filter(Run.status.in_(["queued", "running", "blocked_for_approval"]))
            .order_by(Run.created_at.asc())
            .limit(max(1, self._config.max_concurrent_runs * 4))
            .all()
        )
        for candidate in candidates:
            updated = (
                session.query(Run)
                .filter(
                    Run.run_id == candidate.run_id,
                    Run.status.in_(["queued", "running", "blocked_for_approval"]),
                    or_(
                        Run.claimed_by.is_(None),
                        Run.claimed_by == self._runner_id,
                        Run.claim_expires_at.is_(None),
                        Run.claim_expires_at < now,
                    ),
                )
                .update(
                    {"claimed_by": self._runner_id, "claim_expires_at": lease_until},
                    synchronize_session=False,
                )
            )
            if updated == 1:
                session.commit()
                return session.query(Run).filter(Run.run_id == candidate.run_id).one_or_none()
        return None

    def _renew_claim(self, session: Session, run: Run) -> bool:
        lease_until = datetime.utcnow() + timedelta(seconds=max(30, self._config.run_claim_ttl_seconds))
        updated = (
            session.query(Run)
            .filter(Run.run_id == run.run_id, Run.claimed_by == self._runner_id)
            .update({"claim_expires_at": lease_until}, synchronize_session=False)
        )
        session.commit()
        return updated == 1

    def _clear_claim(self, session: Session, run: Run) -> None:
        run.claimed_by = None
        run.claim_expires_at = None
        session.add(run)
        session.commit()

    def _run_timed_out(self, run: Run) -> bool:
        if run.started_at is None:
            return False
        elapsed = datetime.utcnow() - run.started_at
        return int(elapsed.total_seconds() * 1000) > self._config.run_timeout_ms

    def _mark_run_timeout(self, session: Session, run: Run) -> None:
        run.status = "failed"
        run.error_code = "RUN_TIMEOUT"
        run.error_message = f"Run exceeded wall-clock timeout of {self._config.run_timeout_ms}ms"
        run.finished_at = datetime.utcnow()
        run.claimed_by = None
        run.claim_expires_at = None
        session.add(run)
        session.commit()
        RUNS_FINISHED.labels(plan_id=run.plan_id, status="failed").inc()

    def _task_row(self, session: Session, run_id: str, task_id: str) -> RunTask | None:
        return session.query(RunTask).filter(RunTask.run_id == run_id, RunTask.task_id == task_id).one_or_none()

    def _ensure_approval(self, session: Session, run: Run, task_id: str, prompt: str, preview: dict[str, Any]) -> RunApproval:
        approval = (
            session.query(RunApproval)
            .filter(RunApproval.run_id == run.run_id, RunApproval.task_id == task_id)
            .one_or_none()
        )
        if approval:
            return approval

        approval = RunApproval(
            approval_id=str(uuid.uuid4()),
            run_id=run.run_id,
            task_id=task_id,
            status="pending",
            prompt=prompt,
            preview_json=preview,
        )
        session.add(approval)
        session.commit()
        return approval

    def _task_has_side_effect(self, task) -> bool:
        if task.type in SIDE_EFFECT_TYPES:
            return True
        if task.type == "http.request":
            method = str(task.input.get("method", "GET")).upper()
            return method not in HTTP_SAFE_METHODS
        return False

    def _process_once(self) -> None:
        with self._session_factory() as session:
            pending_count = session.query(RunApproval).filter(RunApproval.status == "pending").count()
            APPROVALS_PENDING.set(pending_count)

            run = self._claim_next_run(session)
            if not run:
                return

            if run.status == "blocked_for_approval":
                pending = (
                    session.query(RunApproval)
                    .filter(RunApproval.run_id == run.run_id, RunApproval.status == "pending")
                    .count()
                )
                if pending > 0:
                    self._clear_claim(session, run)
                    return
                run.status = "queued"
                session.add(run)
                session.commit()

            self._execute_run(session, run)

    def _execute_run(self, session: Session, run: Run) -> None:
        if not self._renew_claim(session, run):
            logger.warning("run.claim_lost run_id=%s", run.run_id)
            return

        plan = load_plan(self._config.plans_root, run.plan_id)
        if run.plan_hash != hash_plan(plan):
            run.status = "failed"
            run.error_code = "PLAN_HASH_MISMATCH"
            run.error_message = "Plan definition changed after run creation"
            run.finished_at = datetime.utcnow()
            run.claimed_by = None
            run.claim_expires_at = None
            session.add(run)
            session.commit()
            RUNS_FINISHED.labels(plan_id=run.plan_id, status="failed").inc()
            return

        if run.started_at is None:
            run.started_at = datetime.utcnow()
        if self._run_timed_out(run):
            self._mark_run_timeout(session, run)
            return

        run.status = "running"
        session.add(run)
        session.commit()

        targets = {t.target_id: t.model_dump() for t in plan.targets}
        state: dict[str, Any] = {}

        existing = session.query(RunTask).filter(RunTask.run_id == run.run_id, RunTask.status == "succeeded").all()
        for row in existing:
            if row.output_json is not None:
                state[row.task_id] = row.output_json

        try:
            for index, task in enumerate(plan.tasks):
                if not self._renew_claim(session, run):
                    raise RuntimeError("run claim lost during execution")
                if self._run_timed_out(run):
                    self._mark_run_timeout(session, run)
                    return

                row = self._task_row(session, run.run_id, task.id)
                if row and row.status == "succeeded":
                    if row.output_json is not None:
                        state[task.id] = row.output_json
                    continue

                for dep in task.depends_on:
                    dep_row = self._task_row(session, run.run_id, dep)
                    if dep_row is None or dep_row.status != "succeeded":
                        raise RuntimeError(f"Dependency not satisfied for {task.id}: {dep}")

                requires_approval = task.requires_approval or (
                    self._config.policy.side_effects_require_approval and self._task_has_side_effect(task)
                )

                if requires_approval:
                    prompt = (task.approval or {}).get("prompt") if task.approval else None
                    prompt = prompt or f"Approve side effect task '{task.name}' ({task.type})"
                    preview = {"task_id": task.id, "task_name": task.name, "task_type": task.type, "input": task.input}
                    approval = self._ensure_approval(session, run, task.id, prompt, preview)

                    if approval.status == "pending":
                        run.status = "blocked_for_approval"
                        run.claimed_by = None
                        run.claim_expires_at = None
                        session.add(run)
                        session.commit()
                        return
                    if approval.status == "denied":
                        run.status = "failed"
                        run.error_code = "APPROVAL_DENIED"
                        run.error_message = f"Approval denied for task {task.id}"
                        run.finished_at = datetime.utcnow()
                        run.claimed_by = None
                        run.claim_expires_at = None
                        session.add(run)
                        session.commit()
                        RUNS_FINISHED.labels(plan_id=run.plan_id, status="failed").inc()
                        return

                retry = RetryPolicy(
                    attempts=min(task.max_attempts, self._config.retry.attempts),
                    min_delay_ms=self._config.retry.min_delay_ms,
                    max_delay_ms=self._config.retry.max_delay_ms,
                    jitter=self._config.retry.jitter,
                )

                if row is None:
                    row = RunTask(
                        task_run_id=str(uuid.uuid4()),
                        run_id=run.run_id,
                        task_id=task.id,
                        task_index=index,
                        task_name=task.name,
                        task_type=task.type,
                        status="running",
                        attempt=0,
                        max_attempts=task.max_attempts,
                        idempotent=task.idempotent,
                        requires_approval=requires_approval,
                        input_json=task.input,
                    )
                    session.add(row)
                    session.commit()

                ctx = TaskExecutionContext(
                    config=self._config,
                    params=run.params_json,
                    targets=targets,
                    state=state,
                )

                task_start = time.perf_counter()
                output = execute_task(
                    task_type=task.type,
                    task_input=task.input,
                    ctx=ctx,
                    timeout_ms=task.timeout_ms or self._config.default_timeout_ms,
                    idempotent=task.idempotent,
                    retry=retry,
                )
                TASK_DURATION.labels(task_type=task.type).observe(time.perf_counter() - task_start)

                row.status = "succeeded"
                row.attempt = row.attempt + 1
                row.started_at = row.started_at or datetime.utcnow()
                row.finished_at = datetime.utcnow()
                row.output_json = output
                session.add(row)
                session.commit()

                state[task.id] = output
                if task.output and task.output.get("save_as"):
                    state[str(task.output["save_as"])] = output

                kind = (task.output or {}).get("artifact_kind") or task.type
                persist_artifact(
                    session=session,
                    artifacts_root=self._config.artifacts_root,
                    run_id=run.run_id,
                    kind=kind,
                    payload=output,
                    content_type="application/json",
                    metadata={"task_id": task.id},
                )

            run.status = "succeeded"
            run.finished_at = datetime.utcnow()
            run.claimed_by = None
            run.claim_expires_at = None
            session.add(run)
            session.commit()
            RUNS_FINISHED.labels(plan_id=run.plan_id, status="succeeded").inc()
            SCANS_TOTAL.labels(broker=run.plan_id, result="completed").inc()

        except Exception as exc:
            run.status = "failed"
            run.error_code = "TASK_EXECUTION_FAILED"
            run.error_message = str(exc)
            run.finished_at = datetime.utcnow()
            run.claimed_by = None
            run.claim_expires_at = None
            session.add(run)
            session.commit()
            RUNS_FINISHED.labels(plan_id=run.plan_id, status="failed").inc()
            SCANS_TOTAL.labels(broker=run.plan_id, result="failed").inc()
            logger.exception("run.failed run_id=%s", run.run_id)
