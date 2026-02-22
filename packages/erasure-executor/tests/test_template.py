"""Tests for template rendering."""

from erasure_executor.utils.template import get_path, render_string, resolve_value


def test_get_path_simple():
    data = {"a": {"b": {"c": "hello"}}}
    assert get_path(data, "a.b.c") == "hello"


def test_get_path_missing():
    data = {"a": {"b": 1}}
    assert get_path(data, "a.c", "default") == "default"


def test_render_string():
    ctx = {"params": {"name": "Jane Doe", "city": "Chicago"}}
    result = render_string("Hello {{params.name}} from {{params.city}}", ctx)
    assert result == "Hello Jane Doe from Chicago"


def test_render_string_missing_key():
    ctx = {"params": {}}
    result = render_string("Hello {{params.name}}", ctx)
    assert result == "Hello "


def test_resolve_value_dict():
    ctx = {"params": {"x": "1"}}
    result = resolve_value({"key": "{{params.x}}"}, ctx)
    assert result == {"key": "1"}


def test_resolve_value_list():
    ctx = {"params": {"x": "1"}}
    result = resolve_value(["{{params.x}}", "literal"], ctx)
    assert result == ["1", "literal"]


def test_resolve_value_non_string():
    ctx = {}
    assert resolve_value(42, ctx) == 42
    assert resolve_value(True, ctx) is True
