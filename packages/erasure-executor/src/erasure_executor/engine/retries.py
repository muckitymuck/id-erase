from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    min_delay_ms: int = 250
    max_delay_ms: int = 30000
    jitter: float = 0.1


def is_transient_http(status_code: int) -> bool:
    return status_code in {408, 409, 425, 429, 500, 502, 503, 504}


class TaskExecutionError(RuntimeError):
    def __init__(self, message: str, *, transient: bool, status_code: int | None = None):
        super().__init__(message)
        self.transient = transient
        self.status_code = status_code


def _sleep_backoff(delay: int, jitter: float, max_delay: int) -> int:
    jitter_factor = 1.0 + random.uniform(-jitter, jitter)
    sleep_ms = min(max_delay, int(delay * jitter_factor))
    time.sleep(sleep_ms / 1000.0)
    return min(max_delay, delay * 2)


def with_retries(fn: Callable[[], T], policy: RetryPolicy, *, idempotent: bool) -> T:
    last_exc: Exception | None = None
    delay = policy.min_delay_ms

    for attempt in range(1, policy.attempts + 1):
        try:
            return fn()
        except TaskExecutionError as exc:
            last_exc = exc
            if not idempotent or not exc.transient or attempt == policy.attempts:
                break
            delay = _sleep_backoff(delay, policy.jitter, policy.max_delay_ms)
        except Exception as exc:
            last_exc = exc
            if not idempotent or attempt == policy.attempts:
                break
            delay = _sleep_backoff(delay, policy.jitter, policy.max_delay_ms)

    raise last_exc if last_exc else RuntimeError("retry failed")
