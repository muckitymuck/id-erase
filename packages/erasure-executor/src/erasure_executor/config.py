from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class RetryConfig:
    attempts: int = 3
    min_delay_ms: int = 500
    max_delay_ms: int = 60000
    jitter: float = 0.15


@dataclass(frozen=True)
class PolicyConfig:
    require_idempotency_key: bool = True
    fail_closed_on_missing_policy: bool = True
    side_effects_require_approval: bool = True
    confidence_threshold: float = 0.8
    require_approval_first_broker: bool = True


@dataclass(frozen=True)
class LlmConfig:
    provider: str = "mock"
    endpoint: str | None = None
    api_key: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class PIIConfig:
    encryption_key: str = ""
    log_redaction: bool = True
    artifact_retention_html_days: int = 7
    artifact_retention_screenshot_days: int = 30
    artifact_retention_confirmation_days: int = -1


@dataclass(frozen=True)
class AgentEmailConfig:
    address: str = ""
    imap_host: str = ""
    imap_port: int = 993
    smtp_host: str = ""
    smtp_port: int = 587
    password: str = ""
    alternative_addresses: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BrowserConfig:
    headless: bool = True
    stealth: bool = True
    default_timeout_ms: int = 15000
    min_delay_ms: int = 1000
    max_delay_ms: int = 3000
    proxy_url: str | None = None
    proxy_username: str | None = None
    proxy_password: str | None = None
    check_robots_txt: bool = True
    rate_limit_per_broker_per_hour: int = 30


@dataclass(frozen=True)
class SchedulerConfig:
    enabled: bool = True
    poll_interval_seconds: int = 300


@dataclass(frozen=True)
class ExecutorConfig:
    bind_host: str
    bind_port: int
    auth_token: str
    database_url: str
    plans_root: str
    artifacts_root: str
    max_concurrent_runs: int
    default_timeout_ms: int
    run_timeout_ms: int
    run_claim_ttl_seconds: int
    retry: RetryConfig = field(default_factory=RetryConfig)
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    pii: PIIConfig = field(default_factory=PIIConfig)
    agent_email: AgentEmailConfig = field(default_factory=AgentEmailConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)


DEFAULT_CONFIG_PATH = Path(os.getenv("ERASURE_EXECUTOR_CONFIG", "/etc/erasure-executor/config.yaml"))


def _resolve_env(value: str) -> str:
    if not value.startswith("env:"):
        return value
    key = value[4:].strip()
    if not key:
        raise ValueError("Invalid env ref: empty key")
    resolved = os.getenv(key)
    if resolved is None or not resolved.strip():
        raise ValueError(f"Environment variable '{key}' referenced in config is missing/empty")
    return resolved.strip()


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing/invalid config.{key}")
    return _resolve_env(value.strip())


def _optional_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Missing/invalid config.{key}")
    if not value.strip():
        return None
    raw = value.strip()
    if raw.startswith("env:"):
        env_key = raw[4:].strip()
        if not env_key:
            raise ValueError(f"Missing/invalid config.{key}")
        resolved = os.getenv(env_key)
        if resolved is None or not resolved.strip():
            return None
        return resolved.strip()
    return raw


def _require_int(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        resolved = _resolve_env(value.strip())
        try:
            return int(resolved)
        except ValueError as exc:
            raise ValueError(f"Missing/invalid config.{key}") from exc
    raise ValueError(f"Missing/invalid config.{key}")


def _coerce_int(value: Any, key: str, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        resolved = _resolve_env(value.strip())
        try:
            return int(resolved)
        except ValueError as exc:
            raise ValueError(f"Missing/invalid config.{key}") from exc
    raise ValueError(f"Missing/invalid config.{key}")


def load_config(path: Path | None = None) -> ExecutorConfig:
    cfg_path = path or DEFAULT_CONFIG_PATH
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Config must be an object")

    retry_raw = raw.get("retry") or {}
    policy_raw = raw.get("policy") or {}
    if not isinstance(retry_raw, dict):
        raise ValueError("config.retry must be an object")
    if not isinstance(policy_raw, dict):
        raise ValueError("config.policy must be an object")

    retry = RetryConfig(
        attempts=int(retry_raw.get("attempts", 3)),
        min_delay_ms=int(retry_raw.get("min_delay_ms", 500)),
        max_delay_ms=int(retry_raw.get("max_delay_ms", 60000)),
        jitter=float(retry_raw.get("jitter", 0.15)),
    )

    policy = PolicyConfig(
        require_idempotency_key=bool(policy_raw.get("require_idempotency_key", True)),
        fail_closed_on_missing_policy=bool(policy_raw.get("fail_closed_on_missing_policy", True)),
        side_effects_require_approval=bool(policy_raw.get("side_effects_require_approval", True)),
        confidence_threshold=float(policy_raw.get("confidence_threshold", 0.8)),
        require_approval_first_broker=bool(policy_raw.get("require_approval_first_broker", True)),
    )

    llm_raw = raw.get("llm") or {}
    if not isinstance(llm_raw, dict):
        raise ValueError("config.llm must be an object")
    llm = LlmConfig(
        provider=str(llm_raw.get("provider", "mock")),
        endpoint=_optional_str(llm_raw, "endpoint"),
        api_key=_optional_str(llm_raw, "api_key"),
        model=_optional_str(llm_raw, "model"),
    )
    if llm.provider not in {"mock", "openai_compatible"}:
        raise ValueError("config.llm.provider must be 'mock' or 'openai_compatible'")
    if llm.provider == "openai_compatible":
        if not llm.endpoint or not llm.api_key or not llm.model:
            raise ValueError("config.llm.provider=openai_compatible requires endpoint, api_key, and model")

    # PII config
    pii_raw = raw.get("pii") or {}
    if not isinstance(pii_raw, dict):
        pii_raw = {}
    retention = pii_raw.get("artifact_retention") or {}
    pii = PIIConfig(
        encryption_key=_optional_str(pii_raw, "encryption_key") or "",
        log_redaction=bool(pii_raw.get("log_redaction", True)),
        artifact_retention_html_days=int(retention.get("html_days", 7)),
        artifact_retention_screenshot_days=int(retention.get("screenshot_days", 30)),
        artifact_retention_confirmation_days=int(retention.get("confirmation_days", -1)),
    )

    # Agent email config
    email_raw = raw.get("agent_email") or {}
    if not isinstance(email_raw, dict):
        email_raw = {}
    alt_emails_raw = email_raw.get("alternative_addresses") or []
    alt_emails = []
    for ae in alt_emails_raw:
        if isinstance(ae, str) and ae.strip():
            resolved = _optional_str({"v": ae}, "v")
            if resolved:
                alt_emails.append(resolved)
    agent_email = AgentEmailConfig(
        address=_optional_str(email_raw, "address") or "",
        imap_host=_optional_str(email_raw, "imap_host") or "",
        imap_port=_coerce_int(email_raw.get("imap_port"), "agent_email.imap_port", 993),
        smtp_host=_optional_str(email_raw, "smtp_host") or "",
        smtp_port=_coerce_int(email_raw.get("smtp_port"), "agent_email.smtp_port", 587),
        password=_optional_str(email_raw, "password") or "",
        alternative_addresses=alt_emails,
    )

    # Browser config
    browser_raw = raw.get("browser") or {}
    if not isinstance(browser_raw, dict):
        browser_raw = {}
    browser = BrowserConfig(
        headless=bool(browser_raw.get("headless", True)),
        stealth=bool(browser_raw.get("stealth", True)),
        default_timeout_ms=_coerce_int(browser_raw.get("default_timeout_ms"), "browser.default_timeout_ms", 15000),
        min_delay_ms=_coerce_int(browser_raw.get("min_delay_ms"), "browser.min_delay_ms", 1000),
        max_delay_ms=_coerce_int(browser_raw.get("max_delay_ms"), "browser.max_delay_ms", 3000),
        proxy_url=_optional_str(browser_raw, "proxy_url"),
        proxy_username=_optional_str(browser_raw, "proxy_username"),
        proxy_password=_optional_str(browser_raw, "proxy_password"),
        check_robots_txt=bool(browser_raw.get("check_robots_txt", True)),
        rate_limit_per_broker_per_hour=_coerce_int(
            browser_raw.get("rate_limit_per_broker_per_hour"), "browser.rate_limit_per_broker_per_hour", 30
        ),
    )

    # Scheduler config
    scheduler_raw = raw.get("scheduler") or {}
    if not isinstance(scheduler_raw, dict):
        scheduler_raw = {}
    scheduler = SchedulerConfig(
        enabled=bool(scheduler_raw.get("enabled", True)),
        poll_interval_seconds=_coerce_int(
            scheduler_raw.get("poll_interval_seconds"), "scheduler.poll_interval_seconds", 300
        ),
    )

    run_timeout_ms = _coerce_int(raw.get("run_timeout_ms", 3600000), "run_timeout_ms")
    run_claim_ttl_seconds = _coerce_int(raw.get("run_claim_ttl_seconds", 600), "run_claim_ttl_seconds")
    if run_timeout_ms < 1000:
        raise ValueError("config.run_timeout_ms must be >= 1000")
    if run_claim_ttl_seconds < 30:
        raise ValueError("config.run_claim_ttl_seconds must be >= 30")

    return ExecutorConfig(
        bind_host=_require_str(raw, "bind_host"),
        bind_port=_require_int(raw, "bind_port"),
        auth_token=_require_str(raw, "auth_token"),
        database_url=_require_str(raw, "database_url"),
        plans_root=_require_str(raw, "plans_root"),
        artifacts_root=_require_str(raw, "artifacts_root"),
        max_concurrent_runs=_require_int(raw, "max_concurrent_runs"),
        default_timeout_ms=_require_int(raw, "default_timeout_ms"),
        run_timeout_ms=run_timeout_ms,
        run_claim_ttl_seconds=run_claim_ttl_seconds,
        retry=retry,
        policy=policy,
        llm=llm,
        pii=pii,
        agent_email=agent_email,
        browser=browser,
        scheduler=scheduler,
    )
