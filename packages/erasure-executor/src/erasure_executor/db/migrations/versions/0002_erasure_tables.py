"""Add id-erase tables: pii_profiles, broker_listings, removal_actions, human_action_queue, scan_schedule

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pii_profiles",
        sa.Column("profile_id", sa.String, primary_key=True),
        sa.Column("label", sa.String, nullable=False, server_default="default"),
        sa.Column("encrypted_data", sa.LargeBinary, nullable=False),
        sa.Column("encryption_iv", sa.LargeBinary, nullable=False),
        sa.Column("encryption_tag", sa.LargeBinary, nullable=False),
        sa.Column("data_hash", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "broker_listings",
        sa.Column("listing_id", sa.String, primary_key=True),
        sa.Column("broker_id", sa.String, nullable=False, index=True),
        sa.Column("profile_id", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="found", index=True),
        sa.Column("listing_url", sa.Text, nullable=True),
        sa.Column("listing_snapshot", sa.JSON, nullable=True),
        sa.Column("matched_fields", sa.JSON, nullable=True),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("discovered_at", sa.DateTime, nullable=False),
        sa.Column("removal_sent_at", sa.DateTime, nullable=True),
        sa.Column("verified_at", sa.DateTime, nullable=True),
        sa.Column("last_checked_at", sa.DateTime, nullable=True),
        sa.Column("recheck_after", sa.DateTime, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("idx_broker_listings_recheck", "broker_listings", ["recheck_after"])

    op.create_table(
        "removal_actions",
        sa.Column("action_id", sa.String, primary_key=True),
        sa.Column("listing_id", sa.String, nullable=False, index=True),
        sa.Column("run_id", sa.String, nullable=True),
        sa.Column("action_type", sa.String, nullable=False),
        sa.Column("request_summary", sa.Text, nullable=True),
        sa.Column("response_status", sa.String, nullable=True),
        sa.Column("confirmation_id", sa.String, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "human_action_queue",
        sa.Column("queue_id", sa.String, primary_key=True),
        sa.Column("listing_id", sa.String, nullable=True),
        sa.Column("broker_id", sa.String, nullable=False),
        sa.Column("action_needed", sa.Text, nullable=False),
        sa.Column("instructions", sa.Text, nullable=True),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("completed_notes", sa.Text, nullable=True),
    )
    op.create_index("idx_human_queue_status", "human_action_queue", ["status"])

    op.create_table(
        "scan_schedule",
        sa.Column("schedule_id", sa.String, primary_key=True),
        sa.Column("broker_id", sa.String, nullable=False),
        sa.Column("profile_id", sa.String, nullable=False),
        sa.Column("scan_type", sa.String, nullable=False, server_default="discovery"),
        sa.Column("next_run_at", sa.DateTime, nullable=False),
        sa.Column("last_run_id", sa.String, nullable=True),
        sa.Column("last_run_at", sa.DateTime, nullable=True),
        sa.Column("interval_days", sa.Integer, nullable=False, server_default="30"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("idx_scan_schedule_next", "scan_schedule", ["next_run_at"])


def downgrade() -> None:
    op.drop_table("scan_schedule")
    op.drop_table("human_action_queue")
    op.drop_table("removal_actions")
    op.drop_table("broker_listings")
    op.drop_table("pii_profiles")
