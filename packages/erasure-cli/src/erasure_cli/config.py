"""CLI configuration loader."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


DEFAULT_CONFIG_PATH = Path.home() / ".id-erase" / "config.yaml"


@dataclass(frozen=True)
class CLIConfig:
    executor_url: str
    auth_token: str

    @classmethod
    def load(cls, path: Path | None = None) -> CLIConfig:
        """Load config from YAML file or environment variables."""
        # Environment variables take precedence
        url = os.getenv("IDERASE_EXECUTOR_URL")
        token = os.getenv("IDERASE_AUTH_TOKEN")

        if url and token:
            return cls(executor_url=url, auth_token=token)

        cfg_path = path or DEFAULT_CONFIG_PATH
        if cfg_path.exists():
            raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return cls(
                    executor_url=raw.get("executor_url", "http://localhost:8080"),
                    auth_token=raw.get("auth_token", ""),
                )

        return cls(
            executor_url=url or "http://localhost:8080",
            auth_token=token or "",
        )
