"""Initial schema — core execution tables

Revision ID: 0001
Revises:
Create Date: 2026-02-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("run_id", sa.String, primary_key=True),
        sa.Column("plan_id", sa.String, nullable=False, index=True),
        sa.Column("plan_hash", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, index=True),
        sa.Column("requested_by", sa.String, nullable=True),
        sa.Column("idempotency_key", sa.String, unique=True, index=True, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("claimed_by", sa.String, index=True, nullable=True),
        sa.Column("claim_expires_at", sa.DateTime, nullable=True),
        sa.Column("params_json", sa.JSON, default=dict),
        sa.Column("result_summary_json", sa.JSON, nullable=True),
        sa.Column("error_code", sa.String, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )

    op.create_table(
        "run_tasks",
        sa.Column("task_run_id", sa.String, primary_key=True),
        sa.Column("run_id", sa.String, nullable=False, index=True),
        sa.Column("task_id", sa.String, nullable=False, index=True),
        sa.Column("task_index", sa.Integer, nullable=False),
        sa.Column("task_name", sa.String, nullable=False),
        sa.Column("task_type", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, index=True),
        sa.Column("attempt", sa.Integer, default=0),
        sa.Column("max_attempts", sa.Integer, default=3),
        sa.Column("idempotent", sa.Boolean, default=True),
        sa.Column("requires_approval", sa.Boolean, default=False),
        sa.Column("approval_id", sa.String, index=True, nullable=True),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("input_json", sa.JSON, default=dict),
        sa.Column("output_json", sa.JSON, nullable=True),
        sa.Column("error_code", sa.String, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )

    op.create_table(
        "run_approvals",
        sa.Column("approval_id", sa.String, primary_key=True),
        sa.Column("run_id", sa.String, nullable=False, index=True),
        sa.Column("task_id", sa.String, nullable=False, index=True),
        sa.Column("status", sa.String, nullable=False, index=True),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("preview_json", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("resolved_by", sa.String, nullable=True),
    )

    op.create_table(
        "run_artifacts",
        sa.Column("artifact_id", sa.String, primary_key=True),
        sa.Column("run_id", sa.String, nullable=False, index=True),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("content_type", sa.String, nullable=False),
        sa.Column("uri", sa.Text, nullable=False),
        sa.Column("metadata_json", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("run_artifacts")
    op.drop_table("run_approvals")
    op.drop_table("run_tasks")
    op.drop_table("runs")
