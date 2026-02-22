from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

RUNS_STARTED = Counter("erasure_runs_started_total", "Total run starts", ["plan_id"])
RUNS_FINISHED = Counter("erasure_runs_finished_total", "Total run terminal states", ["plan_id", "status"])
TASK_DURATION = Histogram("erasure_task_duration_seconds", "Task duration", ["task_type"])
APPROVALS_PENDING = Gauge("erasure_approvals_pending", "Pending approvals")
LISTINGS_TOTAL = Gauge("erasure_listings_total", "Broker listings by status", ["broker", "status"])
REMOVALS_TOTAL = Counter("erasure_removals_total", "Removal attempts", ["broker", "result"])
SCANS_TOTAL = Counter("erasure_scans_total", "Scan runs", ["broker", "result"])
HUMAN_QUEUE_PENDING = Gauge("erasure_human_queue_pending", "Pending human actions")
MATCH_CONFIDENCE = Histogram("erasure_match_confidence", "Match confidence scores", ["broker"])
