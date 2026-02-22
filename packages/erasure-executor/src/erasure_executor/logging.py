from __future__ import annotations

import json
import logging
import re
import sys
from typing import Any


class RedactingFilter(logging.Filter):
    """Strips PII patterns from log records."""

    PATTERNS = [
        (re.compile(r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b"), "[SSN-REDACTED]"),
        (re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"), "[PHONE-REDACTED]"),
        (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL-REDACTED]"),
        (re.compile(r"\b\d{5}(?:-\d{4})?\b"), "[ZIP-REDACTED]"),
    ]

    def __init__(self, additional_terms: list[str] | None = None):
        super().__init__()
        self._additional = additional_terms or []

    def set_additional_terms(self, terms: list[str]) -> None:
        self._additional = [t for t in terms if t and len(t) > 2]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern, replacement in self.PATTERNS:
            msg = pattern.sub(replacement, msg)
        for term in self._additional:
            if term and len(term) > 2:
                msg = msg.replace(term, "[PII-REDACTED]")
        record.msg = msg
        record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


_redacting_filter = RedactingFilter()


def configure_logging(redact: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    if redact:
        root.addFilter(_redacting_filter)


def set_redaction_terms(terms: list[str]) -> None:
    """Add PII terms to the global redaction filter."""
    _redacting_filter.set_additional_terms(terms)
