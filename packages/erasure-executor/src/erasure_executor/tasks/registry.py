from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import jsonschema

from erasure_executor.connectors.http import HttpConnector
from erasure_executor.connectors.scraper import extract_by_selectors, parse_page
from erasure_executor.config import ExecutorConfig
from erasure_executor.engine.retries import RetryPolicy, TaskExecutionError, is_transient_http, with_retries
from erasure_executor.utils.template import get_path, resolve_value

logger = logging.getLogger(__name__)


@dataclass
class TaskExecutionContext:
    config: ExecutorConfig
    params: dict[str, Any]
    targets: dict[str, dict[str, Any]]
    state: dict[str, Any]


def _value_from_ref(ref: str, ctx: TaskExecutionContext) -> Any:
    if ref in ctx.state:
        return ctx.state[ref]
    value = get_path({"params": ctx.params, "targets": ctx.targets, "state": ctx.state}, ref)
    if value is not None:
        return value
    return None


# ---------------------------------------------------------------------------
# http.request
# ---------------------------------------------------------------------------

def _execute_http(task_input: dict[str, Any], ctx: TaskExecutionContext, timeout_ms: int) -> dict[str, Any]:
    target_id = task_input.get("target_id")
    target = ctx.targets.get(target_id, {}) if isinstance(target_id, str) else {}

    base_url = task_input.get("base_url") or target.get("base_url")
    if not base_url:
        raise ValueError("http.request requires base_url or target_id with base_url")

    method = str(task_input.get("method", "GET"))
    path = str(task_input.get("path", "/"))
    headers = task_input.get("headers")
    params = task_input.get("params")
    json_body = task_input.get("json_body")

    url = base_url.rstrip("/") + "/" + path.lstrip("/")
    connector = HttpConnector(timeout_ms)
    res = connector.request(method, url, headers=headers, params=params, json_body=json_body)
    if res.status_code >= 400:
        raise TaskExecutionError(
            f"http.request failed status={res.status_code} method={method.upper()} url={url}",
            transient=is_transient_http(res.status_code),
            status_code=res.status_code,
        )
    return {
        "url": url,
        "status_code": res.status_code,
        "headers": res.headers,
        "text": res.text[:200000],
        "json": res.json,
    }


# ---------------------------------------------------------------------------
# scrape.static
# ---------------------------------------------------------------------------

def _execute_scrape_static(task_input: dict[str, Any], ctx: TaskExecutionContext) -> dict[str, Any]:
    html = task_input.get("html")
    html_ref = task_input.get("html_ref")

    if isinstance(html_ref, str):
        candidate = _value_from_ref(html_ref, ctx)
        if isinstance(candidate, dict):
            html = candidate.get("text")
        elif isinstance(candidate, str):
            html = candidate

    if not isinstance(html, str) or not html:
        raise ValueError("scrape.static requires html or html_ref")

    selectors = task_input.get("extract")
    if isinstance(selectors, dict):
        return extract_by_selectors(html, selectors)
    return parse_page(html)


# ---------------------------------------------------------------------------
# scrape.rendered
# ---------------------------------------------------------------------------

def _execute_scrape_rendered(task_input: dict[str, Any], ctx: TaskExecutionContext, timeout_ms: int) -> dict[str, Any]:
    from erasure_executor.connectors.browser import BrowserConnector, run_browser_task

    target_id = task_input.get("target_id")
    target = ctx.targets.get(target_id, {}) if isinstance(target_id, str) else {}
    base_url = task_input.get("base_url") or target.get("base_url", "")

    url_template = task_input.get("url_template", "/")
    url = base_url.rstrip("/") + url_template if not url_template.startswith("http") else url_template

    wait_for = task_input.get("wait_for")
    extract_selectors = task_input.get("extract", {})
    take_screenshot = task_input.get("screenshot", False)

    browser = BrowserConnector(
        headless=ctx.config.browser.headless,
        stealth=ctx.config.browser.stealth,
    )

    async def _run():
        try:
            page, status = await browser.navigate(url, wait_for=wait_for, timeout_ms=timeout_ms)
            html = await browser.get_html(page)
            extracted = None

            if isinstance(extract_selectors, dict) and extract_selectors:
                # Extract using selectors if a "fields" sub-dict exists
                fields = extract_selectors.get("fields", extract_selectors)
                extracted = await browser.extract(page, fields)

            # Execute actions if defined (fill, click sequences)
            actions = task_input.get("actions", [])
            for action in actions:
                action_type = action.get("type")
                if action_type == "fill":
                    selector = action["selector"]
                    value = action.get("value", "")
                    value_ref = action.get("value_ref")
                    if value_ref:
                        value = str(_value_from_ref(value_ref, ctx) or "")
                    await browser.fill_form(page, [{"selector": selector, "value": value}])
                elif action_type == "click":
                    wait = action.get("wait_for")
                    await browser.click_and_wait(page, action["selector"], wait_for=wait)

            screenshot_path = None
            if take_screenshot:
                import uuid as _uuid
                from pathlib import Path
                sc_dir = Path(ctx.config.artifacts_root) / "screenshots"
                sc_dir.mkdir(parents=True, exist_ok=True)
                screenshot_path = str(sc_dir / f"{_uuid.uuid4()}.png")
                await browser.screenshot(page, screenshot_path)

            return {
                "url": url,
                "status": status,
                "html": html[:200000],
                "extracted": extracted,
                "screenshot_path": screenshot_path,
            }
        finally:
            await browser.close()

    return run_browser_task(_run())


# ---------------------------------------------------------------------------
# llm.json
# ---------------------------------------------------------------------------

def _placeholder_for_schema(schema: dict[str, Any]) -> Any:
    t = schema.get("type")
    if t == "string":
        return "UNSPECIFIED"
    if t == "integer" or t == "number":
        return 0
    if t == "boolean":
        return False
    if t == "array":
        return []
    if t == "object":
        props = schema.get("properties", {})
        required = schema.get("required", [])
        out: dict[str, Any] = {}
        if isinstance(props, dict):
            for k, v in props.items():
                if k in required:
                    out[k] = _placeholder_for_schema(v if isinstance(v, dict) else {})
        return out
    return None


def _parse_json_response(content: str) -> Any:
    text = content.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:].strip()
    return json.loads(text)


def _execute_llm_json(task_input: dict[str, Any], ctx: TaskExecutionContext, timeout_ms: int) -> dict[str, Any]:
    schema = task_input.get("schema")
    source = None
    json_ref = task_input.get("json_ref")
    if isinstance(json_ref, str):
        source = _value_from_ref(json_ref, ctx)

    if ctx.config.llm.provider == "mock":
        if isinstance(schema, dict):
            return {
                "mode": "deterministic_stub",
                "output": _placeholder_for_schema(schema),
                "source_excerpt": str(source)[:400] if source is not None else None,
            }
        return {
            "mode": "deterministic_stub",
            "output": {"summary": "llm.json executed without external model"},
            "source_excerpt": str(source)[:400] if source is not None else None,
        }

    assert ctx.config.llm.endpoint is not None
    assert ctx.config.llm.api_key is not None
    assert ctx.config.llm.model is not None

    connector = HttpConnector(timeout_ms)
    prompt = str(task_input.get("prompt", "")).strip()
    source_excerpt = str(source)[:12000] if source is not None else ""
    schema_json = json.dumps(schema, ensure_ascii=False) if isinstance(schema, dict) else "{}"

    user_message = (
        "Return ONLY JSON that matches the provided schema. "
        "Do not include markdown fences or extra commentary.\n\n"
        f"Instruction:\n{prompt}\n\n"
        f"Schema:\n{schema_json}\n\n"
        f"Source excerpt:\n{source_excerpt}"
    )

    res = connector.request(
        "POST",
        ctx.config.llm.endpoint.rstrip("/") + "/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {ctx.config.llm.api_key}",
            "Content-Type": "application/json",
        },
        json_body={
            "model": ctx.config.llm.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "You are a JSON generation engine. Always return one JSON object and nothing else."},
                {"role": "user", "content": user_message},
            ],
        },
    )
    if res.status_code >= 400:
        raise TaskExecutionError(f"llm.json provider failed status={res.status_code}", transient=is_transient_http(res.status_code), status_code=res.status_code)
    if not isinstance(res.json, dict):
        raise TaskExecutionError("llm.json provider returned non-json body", transient=False)

    choices = res.json.get("choices")
    if not isinstance(choices, list) or not choices:
        raise TaskExecutionError("llm.json provider returned empty choices", transient=False)
    first = choices[0]
    if not isinstance(first, dict):
        raise TaskExecutionError("llm.json provider returned invalid choice", transient=False)
    message = first.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise TaskExecutionError("llm.json provider returned invalid message", transient=False)

    output = _parse_json_response(message["content"])
    if isinstance(schema, dict):
        jsonschema.validate(instance=output, schema=schema)

    return {"mode": "openai_compatible", "model": ctx.config.llm.model, "output": output}


# ---------------------------------------------------------------------------
# Stub task types (implemented in Phase 1)
# ---------------------------------------------------------------------------

def _execute_form_submit(task_input: dict[str, Any], ctx: TaskExecutionContext, timeout_ms: int) -> dict[str, Any]:
    from erasure_executor.connectors.browser import BrowserConnector, run_browser_task
    from erasure_executor.connectors.form import FormConnector

    target_id = task_input.get("target_id")
    target = ctx.targets.get(target_id, {}) if isinstance(target_id, str) else {}
    base_url = task_input.get("base_url") or target.get("base_url", "")

    url_template = task_input.get("url_template", "/")
    url = base_url.rstrip("/") + url_template if not url_template.startswith("http") else url_template

    wait_for = task_input.get("wait_for")
    form_hints = task_input.get("form_hints")
    field_values = task_input.get("fields", {})
    take_screenshot = task_input.get("screenshot", True)

    # Resolve field values from state/params
    resolved_fields = {}
    for k, v in field_values.items():
        if isinstance(v, str) and v.startswith("{{") and v.endswith("}}"):
            ref = v[2:-2].strip()
            resolved = _value_from_ref(ref, ctx)
            resolved_fields[k] = str(resolved) if resolved is not None else ""
        else:
            resolved_fields[k] = str(v)

    browser = BrowserConnector(
        headless=ctx.config.browser.headless,
        stealth=ctx.config.browser.stealth,
    )
    form_connector = FormConnector()

    async def _run():
        try:
            page, status = await browser.navigate(url, wait_for=wait_for, timeout_ms=timeout_ms)

            form = await form_connector.detect_form(page, hints=form_hints)
            if form is None:
                raise TaskExecutionError("form.submit: no form detected on page", transient=False)

            screenshot_base = None
            if take_screenshot:
                import uuid as _uuid
                from pathlib import Path
                sc_dir = Path(ctx.config.artifacts_root) / "screenshots"
                sc_dir.mkdir(parents=True, exist_ok=True)
                screenshot_base = str(sc_dir / str(_uuid.uuid4()))

            # Map field values by selector — form_hints can provide name→selector mapping
            values_by_selector = {}
            selector_map = (form_hints or {}).get("field_map", {})
            for field_name, value in resolved_fields.items():
                selector = selector_map.get(field_name, f"[name='{field_name}']")
                values_by_selector[selector] = value

            result = await form_connector.fill_and_submit(
                page, form, values_by_selector, screenshot_path=screenshot_base,
            )

            return {
                "url": url,
                "form_action": form.action_url,
                "form_method": form.method,
                "fields_submitted": list(resolved_fields.keys()),
                "success": result.success,
                "error": result.error,
                "screenshot_path": result.screenshot_path,
                "response_excerpt": (result.response_text or "")[:5000],
            }
        finally:
            await browser.close()

    return run_browser_task(_run())


def _execute_email_send(task_input: dict[str, Any], ctx: TaskExecutionContext) -> dict[str, Any]:
    from erasure_executor.connectors.email import EmailConfig, EmailConnector

    ec = ctx.config.agent_email
    if not ec.address or not ec.smtp_host:
        raise ValueError("email.send requires agent_email configuration")

    connector = EmailConnector(EmailConfig(
        address=ec.address, imap_host=ec.imap_host, imap_port=ec.imap_port,
        smtp_host=ec.smtp_host, smtp_port=ec.smtp_port, password=ec.password,
        alternative_addresses=ec.alternative_addresses,
    ))
    return connector.send(
        to=task_input["to"],
        subject=task_input.get("subject", "Data Removal Request"),
        body=task_input.get("body", task_input.get("body_template", "")),
    )


def _execute_email_check(task_input: dict[str, Any], ctx: TaskExecutionContext, timeout_ms: int) -> dict[str, Any]:
    from erasure_executor.connectors.email import EmailConfig, EmailConnector

    ec = ctx.config.agent_email
    if not ec.address or not ec.imap_host:
        raise ValueError("email.check requires agent_email configuration")

    connector = EmailConnector(EmailConfig(
        address=ec.address, imap_host=ec.imap_host, imap_port=ec.imap_port,
        smtp_host=ec.smtp_host, smtp_port=ec.smtp_port, password=ec.password,
        alternative_addresses=ec.alternative_addresses,
    ))
    messages = connector.check_inbox(
        from_filter=task_input.get("from_filter"),
        subject_filter=task_input.get("subject_filter"),
        wait_minutes=int(task_input.get("wait_minutes", 0)),
        poll_interval_seconds=int(task_input.get("poll_interval_seconds", 30)),
    )
    result = {
        "found": len(messages),
        "messages": [
            {"from": m.from_addr, "subject": m.subject, "links": m.links}
            for m in messages
        ],
    }
    if messages and task_input.get("extract_links"):
        all_links = []
        for m in messages:
            all_links.extend(m.links)
        result["links"] = all_links
    return result


def _execute_email_click_verify(task_input: dict[str, Any], ctx: TaskExecutionContext, timeout_ms: int) -> dict[str, Any]:
    link_ref = task_input.get("link_ref")
    link = task_input.get("link")
    if link_ref:
        link = _value_from_ref(link_ref, ctx)
    if not link:
        raise ValueError("email.click_verify requires link or link_ref")

    return _execute_scrape_rendered(
        {"base_url": "", "url_template": str(link), "wait_for": task_input.get("wait_for"), "screenshot": True},
        ctx, timeout_ms,
    )


def _execute_match_identity(task_input: dict[str, Any], ctx: TaskExecutionContext, timeout_ms: int) -> dict[str, Any]:
    from erasure_executor.engine.pii_vault import PIIVault
    from erasure_executor.matching.identity import MatchResult, heuristic_match

    # Load and decrypt profile
    profile_id = task_input.get("profile_id")
    if not profile_id:
        raise ValueError("match.identity requires profile_id")

    profile_ref = task_input.get("profile_ref")
    profile_data = None
    if profile_ref:
        profile_data = _value_from_ref(profile_ref, ctx)

    if not isinstance(profile_data, dict):
        # Load from vault via state (the runner should have decrypted it)
        profile_data = _value_from_ref("profile_data", ctx)
    if not isinstance(profile_data, dict):
        raise ValueError("match.identity: could not resolve profile data from profile_ref or state.profile_data")

    # Get listings to match against
    listings_ref = task_input.get("listings_ref")
    listings = []
    if listings_ref:
        raw = _value_from_ref(listings_ref, ctx)
        if isinstance(raw, list):
            listings = raw
        elif isinstance(raw, dict) and "extracted" in raw:
            # Handle scrape.rendered output format
            listings = _build_listings_from_extracted(raw["extracted"])

    if not listings:
        return {"matched": [], "all_results": [], "count": 0}

    threshold = float(task_input.get("threshold", ctx.config.policy.confidence_threshold))
    llm_threshold_low = float(task_input.get("llm_threshold_low", 0.4))
    llm_threshold_high = float(task_input.get("llm_threshold_high", 0.8))

    results: list[dict[str, Any]] = []
    matched: list[dict[str, Any]] = []

    for listing in listings:
        if not isinstance(listing, dict):
            continue
        match_result = heuristic_match(listing, profile_data)

        result_dict = {
            "listing": listing,
            "confidence": match_result.confidence,
            "matched_fields": match_result.matched_fields,
            "above_threshold": match_result.confidence >= threshold,
        }

        # LLM verification for borderline cases
        if llm_threshold_low <= match_result.confidence <= llm_threshold_high:
            if ctx.config.llm.provider != "mock":
                try:
                    llm_result = _llm_verify_match(match_result, profile_data, ctx, timeout_ms)
                    result_dict["llm_verified"] = llm_result.get("is_match", False)
                    result_dict["llm_confidence"] = llm_result.get("confidence", match_result.confidence)
                    result_dict["confidence"] = llm_result.get("confidence", match_result.confidence)
                    result_dict["above_threshold"] = result_dict["confidence"] >= threshold
                except Exception:
                    logger.exception("match.identity llm_verify failed, using heuristic score")

        results.append(result_dict)
        if result_dict["above_threshold"]:
            matched.append(result_dict)

    return {"matched": matched, "all_results": results, "count": len(matched)}


def _build_listings_from_extracted(extracted: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert selector-extracted data into listing dicts.

    Input format (from scrape.rendered extract):
        {"names": ["Jane Doe", "John Doe"], "locations": ["Chicago, IL", ...], ...}
    Output:
        [{"name": "Jane Doe", "location": "Chicago, IL"}, ...]
    """
    # Map common extracted field names to listing field names
    field_map = {
        "names": "name", "name": "name",
        "locations": "location", "location": "location",
        "ages": "age", "age": "age",
        "phones": "phone", "phone": "phone",
        "links": "profile_url", "urls": "profile_url",
    }

    mapped: dict[str, list] = {}
    max_len = 0
    for key, values in extracted.items():
        if not isinstance(values, list):
            continue
        field_name = field_map.get(key, key)
        mapped[field_name] = values
        max_len = max(max_len, len(values))

    if max_len == 0:
        return []

    listings = []
    for i in range(max_len):
        listing = {}
        for field_name, values in mapped.items():
            if i < len(values):
                listing[field_name] = values[i]
        listings.append(listing)
    return listings


def _llm_verify_match(
    match_result: MatchResult,
    profile: dict[str, Any],
    ctx: TaskExecutionContext,
    timeout_ms: int,
) -> dict[str, Any]:
    """Use LLM to verify a borderline match."""
    prompt = (
        "You are verifying whether a data broker listing matches a specific person. "
        "Compare the listing data against the profile and determine if they are the same person. "
        "Consider name variations, location history, age, and any other available data."
    )
    schema = {
        "type": "object",
        "properties": {
            "is_match": {"type": "boolean"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "reasoning": {"type": "string"},
        },
        "required": ["is_match", "confidence", "reasoning"],
    }
    # Build source with redacted profile (just enough for matching)
    safe_profile = {
        "full_name": profile.get("full_name", ""),
        "aliases": profile.get("aliases", []),
        "addresses": [
            {"city": a.get("city", ""), "state": a.get("state", "")}
            for a in (profile.get("addresses") or [])
            if isinstance(a, dict)
        ],
        "has_dob": bool(profile.get("date_of_birth")),
        "relative_count": len(profile.get("relatives", [])),
    }

    llm_input = {
        "prompt": prompt,
        "schema": schema,
        "json_ref": None,
    }

    # Inject source data as context
    source = {
        "listing": match_result.listing_data,
        "profile_summary": safe_profile,
        "heuristic_confidence": match_result.confidence,
        "matched_fields": match_result.matched_fields,
    }

    # Store source in state temporarily for the LLM task to pick up
    ctx.state["_llm_verify_source"] = source
    llm_input["json_ref"] = "_llm_verify_source"

    return _execute_llm_json(llm_input, ctx, timeout_ms)


def _execute_broker_update_status(task_input: dict[str, Any], ctx: TaskExecutionContext) -> dict[str, Any]:
    from erasure_executor.metrics import LISTINGS_TOTAL, REMOVALS_TOTAL

    broker_id = task_input.get("broker_id", "unknown")
    new_status = task_input.get("status", "found")
    profile_id = task_input.get("profile_id")
    listing_url = task_input.get("listing_url")
    confidence = float(task_input.get("confidence", 0.0))
    notes = task_input.get("notes")
    recheck_days = int(task_input.get("recheck_days", 30))
    run_id = task_input.get("run_id")

    # Resolve listing data from refs
    listing_ref = task_input.get("listing_ref")
    listing_data = None
    if listing_ref:
        listing_data = _value_from_ref(listing_ref, ctx)

    # Resolve matched fields from refs
    matched_fields_ref = task_input.get("matched_fields_ref")
    matched_fields = None
    if matched_fields_ref:
        matched_fields = _value_from_ref(matched_fields_ref, ctx)

    # Build the result — actual DB upsert happens when DB session is available
    # For now, structure the data for the runner to persist
    import uuid as _uuid
    from datetime import datetime, timedelta

    listing_id = task_input.get("listing_id") or str(_uuid.uuid4())
    now = datetime.utcnow()

    result = {
        "listing_id": listing_id,
        "broker_id": broker_id,
        "profile_id": profile_id,
        "status": new_status,
        "listing_url": listing_url,
        "confidence": confidence,
        "matched_fields": matched_fields,
        "listing_snapshot": listing_data,
        "notes": notes,
        "recheck_after": (now + timedelta(days=recheck_days)).isoformat() if new_status != "removed" else None,
        "updated_at": now.isoformat(),
    }

    # Set timestamp fields based on status transition
    if new_status == "found":
        result["discovered_at"] = now.isoformat()
    elif new_status == "removal_submitted":
        result["removal_sent_at"] = now.isoformat()
    elif new_status in ("removed", "verified_removed"):
        result["verified_at"] = now.isoformat()

    result["last_checked_at"] = now.isoformat()

    # Record removal action if applicable
    if new_status in ("removal_submitted", "removal_failed"):
        action_type = task_input.get("action_type", "web_form")
        confirmation_id = task_input.get("confirmation_id")
        error_message = task_input.get("error_message")

        result["removal_action"] = {
            "action_id": str(_uuid.uuid4()),
            "listing_id": listing_id,
            "run_id": run_id,
            "action_type": action_type,
            "request_summary": f"Status update to {new_status} for {broker_id}",
            "response_status": new_status,
            "confirmation_id": confirmation_id,
            "error_message": error_message,
        }

        # Update metrics
        metric_result = "succeeded" if new_status == "removal_submitted" else "failed"
        REMOVALS_TOTAL.labels(broker=broker_id, result=metric_result).inc()

    # Update listing gauge metric
    LISTINGS_TOTAL.labels(broker=broker_id, status=new_status).inc()

    logger.info("broker.update_status broker=%s status=%s listing=%s", broker_id, new_status, listing_id)
    return result


def _execute_queue_human_action(task_input: dict[str, Any], ctx: TaskExecutionContext) -> dict[str, Any]:
    """Queue an action for a human operator (phone verify, CAPTCHA, postal mail, etc.).

    The task succeeds immediately — the human action is async.
    The run continues; the human completes the queue item via the API.
    """
    from erasure_executor.metrics import HUMAN_QUEUE_PENDING
    import uuid as _uuid

    broker_id = task_input.get("broker_id", "unknown")
    action_needed = task_input.get("action_needed", "manual action required")
    instructions = task_input.get("instructions")
    priority = int(task_input.get("priority", 0))
    listing_id = task_input.get("listing_id")

    # Resolve instructions from refs if needed
    instructions_ref = task_input.get("instructions_ref")
    if instructions_ref:
        resolved = _value_from_ref(instructions_ref, ctx)
        if isinstance(resolved, str):
            instructions = resolved

    queue_id = str(_uuid.uuid4())

    result = {
        "queue_id": queue_id,
        "broker_id": broker_id,
        "listing_id": listing_id,
        "action_needed": action_needed,
        "instructions": instructions,
        "priority": priority,
        "status": "pending",
    }

    HUMAN_QUEUE_PENDING.inc()
    logger.info("queue.human_action broker=%s action=%s queue_id=%s", broker_id, action_needed, queue_id)
    return result


def _execute_wait_delay(task_input: dict[str, Any], ctx: TaskExecutionContext) -> dict[str, Any]:
    from datetime import datetime, timedelta

    hours = int(task_input.get("hours", 0))
    minutes = int(task_input.get("minutes", 0))
    seconds = int(task_input.get("seconds", 0))
    reason = task_input.get("reason", "")
    total_seconds = (hours * 3600) + (minutes * 60) + seconds

    now = datetime.utcnow()
    resume_at = now + timedelta(seconds=total_seconds)

    # Short delays (< 5 min): sleep inline
    if total_seconds <= 300:
        if total_seconds > 0:
            logger.info("wait.delay inline_sleep seconds=%d reason=%s", total_seconds, reason)
            time.sleep(total_seconds)
        return {
            "delayed_seconds": total_seconds,
            "reason": reason,
            "mode": "inline_sleep",
            "resumed_at": datetime.utcnow().isoformat(),
        }

    # Longer delays: store resume_at for the runner to check
    logger.info("wait.delay deferred seconds=%d resume_at=%s reason=%s", total_seconds, resume_at.isoformat(), reason)
    return {
        "delayed_seconds": total_seconds,
        "reason": reason,
        "mode": "deferred",
        "resume_at": resume_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def execute_task(
    task_type: str,
    task_input: dict[str, Any],
    ctx: TaskExecutionContext,
    timeout_ms: int,
    idempotent: bool,
    retry: RetryPolicy,
) -> dict[str, Any]:
    resolved_input = resolve_value(task_input, {"params": ctx.params, "targets": ctx.targets, "state": ctx.state})

    def _do() -> dict[str, Any]:
        start = time.perf_counter()
        try:
            if task_type == "http.request":
                result = _execute_http(resolved_input, ctx, timeout_ms)
            elif task_type == "scrape.static":
                result = _execute_scrape_static(resolved_input, ctx)
            elif task_type == "scrape.rendered":
                result = _execute_scrape_rendered(resolved_input, ctx, timeout_ms)
            elif task_type == "form.submit":
                result = _execute_form_submit(resolved_input, ctx, timeout_ms)
            elif task_type == "email.send":
                result = _execute_email_send(resolved_input, ctx)
            elif task_type == "email.check":
                result = _execute_email_check(resolved_input, ctx, timeout_ms)
            elif task_type == "email.click_verify":
                result = _execute_email_click_verify(resolved_input, ctx, timeout_ms)
            elif task_type == "match.identity":
                result = _execute_match_identity(resolved_input, ctx, timeout_ms)
            elif task_type == "broker.update_status":
                result = _execute_broker_update_status(resolved_input, ctx)
            elif task_type == "queue.human_action":
                result = _execute_queue_human_action(resolved_input, ctx)
            elif task_type == "wait.delay":
                result = _execute_wait_delay(resolved_input, ctx)
            elif task_type == "llm.json":
                result = _execute_llm_json(resolved_input, ctx, timeout_ms)
            else:
                raise ValueError(f"Unsupported task type: {task_type}")
        finally:
            duration = time.perf_counter() - start
            logger.info("task.execute", extra={"task_type": task_type, "duration_s": duration})

        return result

    return with_retries(_do, retry, idempotent=idempotent)
