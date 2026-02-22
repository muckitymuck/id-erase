from __future__ import annotations

import re
from typing import Any

_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_.\[\]-]+)\s*\}\}")


def get_path(data: dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = data
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def render_string(value: str, ctx: dict[str, Any]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        found = get_path(ctx, key, "")
        if found is None:
            return ""
        return str(found)

    return _PATTERN.sub(repl, value)


def resolve_value(value: Any, ctx: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return render_string(value, ctx)
    if isinstance(value, list):
        return [resolve_value(v, ctx) for v in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            out[k] = resolve_value(v, ctx)
        return out
    return value
