"""Broker catalog loader and validation."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

VALID_REMOVAL_METHODS = {
    "web_form", "web_form_with_email_verify", "web_form_with_phone_verify",
    "account_required", "email", "mail_or_fax", "api",
}

VALID_DIFFICULTIES = {"easy", "medium", "hard"}

VALID_CATEGORIES = {"people-search", "marketing-data", "risk-data", "background-check"}


@dataclass(frozen=True)
class BrokerEntry:
    id: str
    name: str
    category: str
    removal_method: str
    difficulty: str
    plan_file: str | None
    recheck_days: int
    notes: str


def _validate_broker(raw: dict[str, Any], index: int) -> BrokerEntry:
    broker_id = raw.get("id")
    if not isinstance(broker_id, str) or not broker_id.strip():
        raise ValueError(f"Broker at index {index}: missing or empty 'id'")

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Broker '{broker_id}': missing or empty 'name'")

    category = raw.get("category", "")
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Broker '{broker_id}': invalid category '{category}', must be one of {VALID_CATEGORIES}")

    removal_method = raw.get("removal_method", "")
    if removal_method not in VALID_REMOVAL_METHODS:
        raise ValueError(
            f"Broker '{broker_id}': invalid removal_method '{removal_method}', "
            f"must be one of {VALID_REMOVAL_METHODS}"
        )

    difficulty = raw.get("difficulty", "")
    if difficulty not in VALID_DIFFICULTIES:
        raise ValueError(f"Broker '{broker_id}': invalid difficulty '{difficulty}', must be one of {VALID_DIFFICULTIES}")

    plan_file = raw.get("plan_file")
    if plan_file is not None and not isinstance(plan_file, str):
        plan_file = None

    recheck_days = raw.get("recheck_days", 30)
    if not isinstance(recheck_days, int) or recheck_days < 1:
        raise ValueError(f"Broker '{broker_id}': recheck_days must be a positive integer")

    notes = str(raw.get("notes", ""))

    return BrokerEntry(
        id=broker_id.strip(),
        name=name.strip(),
        category=category,
        removal_method=removal_method,
        difficulty=difficulty,
        plan_file=plan_file,
        recheck_days=recheck_days,
        notes=notes,
    )


class BrokerCatalog:
    """Loads and provides access to the broker catalog."""

    def __init__(self, brokers: list[BrokerEntry]):
        self._brokers = {b.id: b for b in brokers}

    @classmethod
    def load(cls, path: Path) -> BrokerCatalog:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "brokers" not in raw:
            raise ValueError(f"Catalog file must contain a 'brokers' list: {path}")

        brokers_raw = raw["brokers"]
        if not isinstance(brokers_raw, list):
            raise ValueError(f"Catalog 'brokers' must be a list: {path}")

        entries = []
        seen_ids: set[str] = set()
        for i, item in enumerate(brokers_raw):
            if not isinstance(item, dict):
                raise ValueError(f"Broker at index {i} must be an object")
            entry = _validate_broker(item, i)
            if entry.id in seen_ids:
                raise ValueError(f"Duplicate broker id: '{entry.id}'")
            seen_ids.add(entry.id)
            entries.append(entry)

        logger.info("catalog.loaded brokers=%d", len(entries))
        return cls(entries)

    def get(self, broker_id: str) -> BrokerEntry | None:
        return self._brokers.get(broker_id)

    def all(self) -> list[BrokerEntry]:
        return list(self._brokers.values())

    def ids(self) -> list[str]:
        return list(self._brokers.keys())

    def __len__(self) -> int:
        return len(self._brokers)

    def __contains__(self, broker_id: str) -> bool:
        return broker_id in self._brokers
