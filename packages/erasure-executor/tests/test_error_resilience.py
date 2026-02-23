"""Tests for browser error handling and resilience."""

import pytest

from erasure_executor.engine.retries import TaskExecutionError


def test_handle_browser_timeout():
    from erasure_executor.tasks.registry import _handle_browser_error

    class FakeTimeoutError(Exception):
        pass

    FakeTimeoutError.__name__ = "TimeoutError"

    with pytest.raises(TaskExecutionError) as exc_info:
        _handle_browser_error(FakeTimeoutError("Timeout 30000ms exceeded"), "https://spokeo.com", ".results")

    assert exc_info.value.transient is True
    assert "timeout" in str(exc_info.value).lower()


def test_handle_browser_selector_not_found():
    from erasure_executor.tasks.registry import _handle_browser_error

    with pytest.raises(TaskExecutionError) as exc_info:
        _handle_browser_error(Exception("selector '.foo' not found on page"), "https://spokeo.com", ".foo")

    assert exc_info.value.transient is False
    assert "selector" in str(exc_info.value).lower()


def test_handle_browser_navigation_failure():
    from erasure_executor.tasks.registry import _handle_browser_error

    with pytest.raises(TaskExecutionError) as exc_info:
        _handle_browser_error(Exception("net::ERR_NAME_NOT_RESOLVED"), "https://bad.example.com")

    assert exc_info.value.transient is True
    assert "navigation" in str(exc_info.value).lower()


def test_handle_browser_robots_blocked():
    from erasure_executor.connectors.browser import RobotsTxtBlocked
    from erasure_executor.tasks.registry import _handle_browser_error

    with pytest.raises(TaskExecutionError) as exc_info:
        _handle_browser_error(RobotsTxtBlocked("blocked"), "https://spokeo.com/robots.txt")

    assert exc_info.value.transient is False
    assert "robots" in str(exc_info.value).lower()


def test_handle_browser_already_wrapped():
    from erasure_executor.tasks.registry import _handle_browser_error

    original = TaskExecutionError("already wrapped", transient=False)
    with pytest.raises(TaskExecutionError) as exc_info:
        _handle_browser_error(original, "https://example.com")

    assert exc_info.value is original


def test_handle_browser_unknown_error():
    from erasure_executor.tasks.registry import _handle_browser_error

    with pytest.raises(TaskExecutionError) as exc_info:
        _handle_browser_error(RuntimeError("something unexpected"), "https://example.com")

    # Unknown errors default to transient
    assert exc_info.value.transient is True
