"""Tests for the id-erase CLI."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from erasure_cli.config import CLIConfig
from erasure_cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_config():
    return CLIConfig(executor_url="http://localhost:8080", auth_token="test-token")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def test_config_from_env(monkeypatch):
    monkeypatch.setenv("IDERASE_EXECUTOR_URL", "http://custom:9090")
    monkeypatch.setenv("IDERASE_AUTH_TOKEN", "env-token")
    cfg = CLIConfig.load()
    assert cfg.executor_url == "http://custom:9090"
    assert cfg.auth_token == "env-token"


def test_config_defaults():
    cfg = CLIConfig.load()
    assert cfg.executor_url == "http://localhost:8080"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health_ok(runner, mock_config):
    with patch("erasure_cli.main.CLIConfig.load", return_value=mock_config):
        with patch("erasure_cli.client.ExecutorClient.healthz", return_value={"ok": True}):
            result = runner.invoke(cli, ["health"])
            assert result.exit_code == 0
            assert "healthy" in result.output


def test_health_unreachable(runner, mock_config):
    with patch("erasure_cli.main.CLIConfig.load", return_value=mock_config):
        with patch("erasure_cli.client.ExecutorClient.healthz", side_effect=Exception("connection refused")):
            result = runner.invoke(cli, ["health"])
            assert result.exit_code != 0
            assert "unreachable" in result.output


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def test_status_list_brokers(runner, mock_config):
    brokers = [
        {
            "broker_id": "spokeo",
            "name": "Spokeo",
            "category": "people-search",
            "difficulty": "medium",
            "listing_counts": {"found": 2, "removal_submitted": 1},
            "next_scan_at": "2026-03-01T00:00:00",
        }
    ]
    with patch("erasure_cli.main.CLIConfig.load", return_value=mock_config):
        with patch("erasure_cli.client.ExecutorClient.list_brokers", return_value=brokers):
            result = runner.invoke(cli, ["status"])
            assert result.exit_code == 0
            assert "spokeo" in result.output
            assert "people-search" in result.output


def test_status_broker_listings(runner, mock_config):
    listings = [
        {
            "listing_id": "abc-123-def-456",
            "broker_id": "spokeo",
            "status": "found",
            "listing_url": "https://spokeo.com/John-Doe",
            "confidence": 0.92,
            "discovered_at": "2026-02-20T12:00:00",
        }
    ]
    with patch("erasure_cli.main.CLIConfig.load", return_value=mock_config):
        with patch("erasure_cli.client.ExecutorClient.list_broker_listings", return_value=listings):
            result = runner.invoke(cli, ["status", "spokeo"])
            assert result.exit_code == 0
            assert "found" in result.output
            assert "0.92" in result.output


def test_status_no_brokers(runner, mock_config):
    with patch("erasure_cli.main.CLIConfig.load", return_value=mock_config):
        with patch("erasure_cli.client.ExecutorClient.list_brokers", return_value=[]):
            result = runner.invoke(cli, ["status"])
            assert result.exit_code == 0
            assert "No brokers found" in result.output


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------

def test_queue_list(runner, mock_config):
    items = [
        {
            "queue_id": "q-abc-123",
            "broker_id": "whitepages",
            "action_needed": "phone_verification",
            "priority": 1,
            "status": "pending",
            "created_at": "2026-02-20T12:00:00",
        }
    ]
    with patch("erasure_cli.main.CLIConfig.load", return_value=mock_config):
        with patch("erasure_cli.client.ExecutorClient.list_queue", return_value=items):
            result = runner.invoke(cli, ["queue", "list"])
            assert result.exit_code == 0
            assert "whitepages" in result.output
            assert "phone_verification" in result.output


def test_queue_complete(runner, mock_config):
    with patch("erasure_cli.main.CLIConfig.load", return_value=mock_config):
        with patch("erasure_cli.client.ExecutorClient.complete_queue_item") as mock_complete:
            result = runner.invoke(cli, ["queue", "complete", "q-123", "--notes", "done"])
            assert result.exit_code == 0
            mock_complete.assert_called_once_with("q-123", notes="done")


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

def test_schedule_list(runner, mock_config):
    schedules = [
        {
            "schedule_id": "s-abc-123",
            "broker_id": "spokeo",
            "scan_type": "discovery",
            "next_run_at": "2026-03-01T00:00:00",
            "interval_days": 30,
            "enabled": True,
        }
    ]
    with patch("erasure_cli.main.CLIConfig.load", return_value=mock_config):
        with patch("erasure_cli.client.ExecutorClient.list_schedule", return_value=schedules):
            result = runner.invoke(cli, ["schedule"])
            assert result.exit_code == 0
            assert "spokeo" in result.output
            assert "30d" in result.output


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

def test_scan_all(runner, mock_config):
    schedules = [
        {"schedule_id": "s-1", "broker_id": "spokeo"},
        {"schedule_id": "s-2", "broker_id": "beenverified"},
    ]
    with patch("erasure_cli.main.CLIConfig.load", return_value=mock_config):
        with patch("erasure_cli.client.ExecutorClient.list_schedule", return_value=schedules):
            with patch("erasure_cli.client.ExecutorClient.trigger_schedule") as mock_trigger:
                result = runner.invoke(cli, ["scan"])
                assert result.exit_code == 0
                assert mock_trigger.call_count == 2
                assert "2 scan(s) triggered" in result.output


def test_scan_single_broker(runner, mock_config):
    schedules = [
        {"schedule_id": "s-1", "broker_id": "spokeo"},
        {"schedule_id": "s-2", "broker_id": "beenverified"},
    ]
    with patch("erasure_cli.main.CLIConfig.load", return_value=mock_config):
        with patch("erasure_cli.client.ExecutorClient.list_schedule", return_value=schedules):
            with patch("erasure_cli.client.ExecutorClient.trigger_schedule") as mock_trigger:
                result = runner.invoke(cli, ["scan", "spokeo"])
                assert result.exit_code == 0
                assert mock_trigger.call_count == 1
                assert "spokeo" in result.output


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def test_profile_create(runner, mock_config):
    response = {
        "profile_id": "p-abc-123",
        "label": "test",
        "data_hash": "sha256:abc...",
    }
    with patch("erasure_cli.main.CLIConfig.load", return_value=mock_config):
        with patch("erasure_cli.client.ExecutorClient.create_profile", return_value=response):
            result = runner.invoke(cli, ["profile", "create", "--name", "John Doe", "--label", "test"])
            assert result.exit_code == 0
            assert "p-abc-123" in result.output


def test_profile_show(runner, mock_config):
    response = {
        "profile_id": "p-abc-123",
        "label": "default",
        "data_hash": "sha256:abc...",
        "created_at": "2026-02-20T12:00:00",
        "updated_at": "2026-02-20T12:00:00",
    }
    with patch("erasure_cli.main.CLIConfig.load", return_value=mock_config):
        with patch("erasure_cli.client.ExecutorClient.get_profile", return_value=response):
            result = runner.invoke(cli, ["profile", "show", "p-abc-123"])
            assert result.exit_code == 0
            assert "p-abc-123" in result.output
            assert "sha256:abc" in result.output


def test_profile_delete_confirmed(runner, mock_config):
    with patch("erasure_cli.main.CLIConfig.load", return_value=mock_config):
        with patch("erasure_cli.client.ExecutorClient.delete_profile") as mock_delete:
            result = runner.invoke(cli, ["profile", "delete", "p-123", "--yes"])
            assert result.exit_code == 0
            mock_delete.assert_called_once_with("p-123")


# ---------------------------------------------------------------------------
# Table formatter
# ---------------------------------------------------------------------------

def test_table_formatter():
    from erasure_cli.main import _table
    output = _table(["Name", "Age"], [["Alice", "30"], ["Bob", "25"]])
    assert "Name" in output
    assert "Alice" in output
    assert "---" in output
