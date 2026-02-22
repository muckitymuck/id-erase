"""Tests for configuration loading."""

import os
import tempfile
from pathlib import Path

import pytest

from erasure_executor.config import load_config


MINIMAL_CONFIG = """
bind_host: "0.0.0.0"
bind_port: 8080
auth_token: "test-token"
database_url: "postgresql+psycopg://user:pass@localhost:5432/test"
plans_root: "/plans"
artifacts_root: "/artifacts"
max_concurrent_runs: 4
default_timeout_ms: 60000
run_timeout_ms: 3600000
run_claim_ttl_seconds: 300
"""


def _write_config(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


def test_load_minimal_config():
    path = _write_config(MINIMAL_CONFIG)
    try:
        config = load_config(path)
        assert config.bind_host == "0.0.0.0"
        assert config.bind_port == 8080
        assert config.auth_token == "test-token"
        assert config.max_concurrent_runs == 4
        assert config.policy.confidence_threshold == 0.8
        assert config.pii.log_redaction is True
        assert config.browser.headless is True
        assert config.scheduler.enabled is True
    finally:
        os.unlink(path)


def test_load_config_with_env_vars():
    os.environ["TEST_TOKEN"] = "env-resolved-token"
    os.environ["TEST_DB_URL"] = "postgresql+psycopg://a:b@localhost/test"
    config_text = MINIMAL_CONFIG.replace("test-token", "env:TEST_TOKEN").replace(
        "postgresql+psycopg://user:pass@localhost:5432/test", "env:TEST_DB_URL"
    )
    path = _write_config(config_text)
    try:
        config = load_config(path)
        assert config.auth_token == "env-resolved-token"
        assert "localhost" in config.database_url
    finally:
        os.unlink(path)
        del os.environ["TEST_TOKEN"]
        del os.environ["TEST_DB_URL"]


def test_missing_required_field():
    config_text = """
bind_host: "0.0.0.0"
bind_port: 8080
"""
    path = _write_config(config_text)
    try:
        with pytest.raises(ValueError):
            load_config(path)
    finally:
        os.unlink(path)


def test_pii_config_defaults():
    path = _write_config(MINIMAL_CONFIG)
    try:
        config = load_config(path)
        assert config.pii.encryption_key == ""
        assert config.pii.log_redaction is True
        assert config.pii.artifact_retention_html_days == 7
        assert config.pii.artifact_retention_screenshot_days == 30
    finally:
        os.unlink(path)
