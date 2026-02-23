"""id-erase CLI — command-line interface for the erasure executor."""
from __future__ import annotations

import json
import sys
from typing import Any

import click

from erasure_cli.client import ExecutorClient
from erasure_cli.config import CLIConfig


def _get_client(ctx: click.Context) -> ExecutorClient:
    cfg = ctx.obj or CLIConfig.load()
    if not cfg.auth_token:
        click.echo("Error: auth_token not configured. Set IDERASE_AUTH_TOKEN or configure ~/.id-erase/config.yaml", err=True)
        sys.exit(1)
    return ExecutorClient(cfg.executor_url, cfg.auth_token)


def _table(headers: list[str], rows: list[list[str]], col_widths: list[int] | None = None) -> str:
    """Simple ASCII table formatter."""
    if not col_widths:
        col_widths = [max(len(h), max((len(str(r[i])) for r in rows), default=0)) for i, h in enumerate(headers)]

    header_line = "  ".join(h.ljust(w) for h, w in zip(headers, col_widths))
    sep_line = "  ".join("-" * w for w in col_widths)
    lines = [header_line, sep_line]
    for row in rows:
        lines.append("  ".join(str(c).ljust(w) for c, w in zip(row, col_widths)))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI root
# ---------------------------------------------------------------------------

@click.group()
@click.option("--url", envvar="IDERASE_EXECUTOR_URL", help="Executor API URL")
@click.option("--token", envvar="IDERASE_AUTH_TOKEN", help="Auth token")
@click.pass_context
def cli(ctx, url, token):
    """id-erase — automated data broker removal agent."""
    cfg = CLIConfig.load()
    if url:
        cfg = CLIConfig(executor_url=url, auth_token=cfg.auth_token)
    if token:
        cfg = CLIConfig(executor_url=cfg.executor_url, auth_token=token)
    ctx.obj = cfg


# ---------------------------------------------------------------------------
# Profile commands
# ---------------------------------------------------------------------------

@cli.group()
def profile():
    """Manage PII profiles."""


@profile.command("create")
@click.option("--label", default="default", help="Profile label")
@click.option("--name", required=True, help="Full legal name")
@click.option("--dob", default=None, help="Date of birth (YYYY-MM-DD)")
@click.option("--city", default=None, help="Current city")
@click.option("--state", default=None, help="Current state (2-letter)")
@click.option("--email", multiple=True, help="Email address(es)")
@click.option("--phone", multiple=True, help="Phone number(s)")
@click.pass_context
def profile_create(ctx, label, name, dob, city, state, email, phone):
    """Create a new PII profile."""
    client = _get_client(ctx)

    profile_data: dict[str, Any] = {"full_name": name}
    if dob:
        profile_data["date_of_birth"] = dob
    if city and state:
        profile_data["addresses"] = [{"street": "", "city": city, "state": state, "current": True}]
    if email:
        profile_data["email_addresses"] = list(email)
    if phone:
        profile_data["phone_numbers"] = [{"number": p, "type": "mobile"} for p in phone]

    try:
        result = client.create_profile(label, profile_data)
        click.echo(f"Profile created: {result['profile_id']}")
        click.echo(f"  Label: {result['label']}")
        click.echo(f"  Hash:  {result['data_hash']}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@profile.command("show")
@click.argument("profile_id")
@click.pass_context
def profile_show(ctx, profile_id):
    """Show profile metadata."""
    client = _get_client(ctx)
    try:
        result = client.get_profile(profile_id)
        click.echo(f"Profile: {result['profile_id']}")
        click.echo(f"  Label:      {result['label']}")
        click.echo(f"  Hash:       {result['data_hash']}")
        click.echo(f"  Created:    {result['created_at']}")
        click.echo(f"  Updated:    {result['updated_at']}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@profile.command("delete")
@click.argument("profile_id")
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.pass_context
def profile_delete(ctx, profile_id, yes):
    """Delete a profile and all associated data."""
    if not yes:
        click.confirm(f"Delete profile {profile_id} and all associated broker data?", abort=True)
    client = _get_client(ctx)
    try:
        client.delete_profile(profile_id)
        click.echo(f"Profile {profile_id} deleted.")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Scan commands
# ---------------------------------------------------------------------------

@cli.command("scan")
@click.argument("broker", required=False)
@click.pass_context
def scan(ctx, broker):
    """Trigger scans. If BROKER is given, trigger only that broker."""
    client = _get_client(ctx)
    try:
        schedules = client.list_schedule()
        triggered = 0
        for s in schedules:
            if broker and s["broker_id"] != broker:
                continue
            client.trigger_schedule(s["schedule_id"])
            click.echo(f"Triggered: {s['broker_id']} (schedule {s['schedule_id'][:8]}...)")
            triggered += 1
        if triggered == 0:
            click.echo("No matching schedules found.")
        else:
            click.echo(f"\n{triggered} scan(s) triggered.")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Status commands
# ---------------------------------------------------------------------------

@cli.command("status")
@click.argument("broker", required=False)
@click.pass_context
def status(ctx, broker):
    """Show broker status. If BROKER is given, show listings for that broker."""
    client = _get_client(ctx)
    try:
        if broker:
            listings = client.list_broker_listings(broker)
            if not listings:
                click.echo(f"No listings found for {broker}.")
                return
            headers = ["Listing ID", "Status", "Confidence", "URL", "Discovered"]
            rows = []
            for l in listings:
                rows.append([
                    l["listing_id"][:12] + "...",
                    l["status"],
                    f"{l['confidence']:.2f}",
                    (l.get("listing_url") or "")[:40],
                    l["discovered_at"][:10] if l.get("discovered_at") else "-",
                ])
            click.echo(_table(headers, rows))
        else:
            brokers = client.list_brokers()
            if not brokers:
                click.echo("No brokers found.")
                return
            headers = ["Broker", "Category", "Found", "Submitted", "Removed", "Next Scan"]
            rows = []
            for b in brokers:
                counts = b.get("listing_counts", {})
                rows.append([
                    b["broker_id"],
                    b["category"],
                    str(counts.get("found", 0)),
                    str(counts.get("removal_submitted", 0)),
                    str(counts.get("removed", 0)),
                    b["next_scan_at"][:10] if b.get("next_scan_at") else "-",
                ])
            click.echo(_table(headers, rows))
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Queue commands
# ---------------------------------------------------------------------------

@cli.group()
def queue():
    """Manage the human action queue."""


@queue.command("list")
@click.pass_context
def queue_list(ctx):
    """Show pending queue items."""
    client = _get_client(ctx)
    try:
        items = client.list_queue()
        if not items:
            click.echo("No pending queue items.")
            return
        headers = ["Queue ID", "Broker", "Action", "Priority", "Created"]
        rows = []
        for i in items:
            rows.append([
                i["queue_id"][:12] + "...",
                i["broker_id"],
                i["action_needed"][:30],
                str(i["priority"]),
                i["created_at"][:10] if i.get("created_at") else "-",
            ])
        click.echo(_table(headers, rows))
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@queue.command("complete")
@click.argument("queue_id")
@click.option("--notes", default=None, help="Completion notes")
@click.pass_context
def queue_complete(ctx, queue_id, notes):
    """Mark a queue item as completed."""
    client = _get_client(ctx)
    try:
        client.complete_queue_item(queue_id, notes=notes)
        click.echo(f"Queue item {queue_id} marked complete.")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Schedule commands
# ---------------------------------------------------------------------------

@cli.command("schedule")
@click.pass_context
def schedule(ctx):
    """Show scan schedule."""
    client = _get_client(ctx)
    try:
        schedules = client.list_schedule()
        if not schedules:
            click.echo("No schedules found.")
            return
        headers = ["Schedule ID", "Broker", "Type", "Next Run", "Interval", "Enabled"]
        rows = []
        for s in schedules:
            rows.append([
                s["schedule_id"][:12] + "...",
                s["broker_id"],
                s.get("scan_type", "discovery"),
                s["next_run_at"][:16] if s.get("next_run_at") else "-",
                f"{s.get('interval_days', 30)}d",
                "yes" if s.get("enabled", True) else "no",
            ])
        click.echo(_table(headers, rows))
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Health command
# ---------------------------------------------------------------------------

@cli.command("health")
@click.pass_context
def health(ctx):
    """Check executor health."""
    client = _get_client(ctx)
    try:
        result = client.healthz()
        if result.get("ok"):
            click.echo("Executor: healthy")
        else:
            click.echo("Executor: unhealthy")
            sys.exit(1)
    except Exception as exc:
        click.echo(f"Executor: unreachable ({exc})", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
