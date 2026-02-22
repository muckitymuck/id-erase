from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FormField:
    selector: str
    field_type: str
    label: str | None
    value: str | None


@dataclass
class FormDefinition:
    action_url: str | None
    method: str
    fields: list[FormField]
    submit_selector: str | None


@dataclass
class SubmitResult:
    success: bool
    response_text: str | None
    screenshot_path: str | None
    error: str | None


class FormConnector:
    """Detects and fills opt-out forms on broker pages."""

    async def detect_form(self, page, hints: dict | None = None) -> FormDefinition | None:
        """Find the opt-out form using hints or heuristics."""
        # Try explicit hints first
        if hints and "form_selector" in hints:
            form_el = await page.query_selector(hints["form_selector"])
            if form_el:
                return await self._parse_form(page, hints["form_selector"])

        # Heuristic: look for forms with opt-out related text
        forms = await page.query_selector_all("form")
        for i, form in enumerate(forms):
            text = (await form.text_content() or "").lower()
            if any(kw in text for kw in ["opt out", "optout", "remove",
                                          "delete", "privacy", "unlist"]):
                return await self._parse_form(page, f"form:nth-of-type({i + 1})")

        # Fallback: first form on page
        if forms:
            return await self._parse_form(page, "form:first-of-type")

        return None

    async def _parse_form(self, page, form_selector: str) -> FormDefinition:
        form = await page.query_selector(form_selector)
        action = await form.get_attribute("action") if form else None
        method = (await form.get_attribute("method") or "POST").upper() if form else "POST"

        fields = []
        inputs = await page.query_selector_all(
            f"{form_selector} input, {form_selector} select, {form_selector} textarea"
        )
        for inp in inputs:
            tag = await inp.evaluate("el => el.tagName.toLowerCase()")
            input_type = await inp.get_attribute("type") or "text"
            name = await inp.get_attribute("name")
            if not name:
                continue
            label_text = await inp.evaluate(
                "el => el.labels?.[0]?.textContent?.trim() || "
                "el.getAttribute('placeholder') || "
                "el.getAttribute('aria-label') || ''"
            )
            fields.append(FormField(
                selector=f"[name='{name}']",
                field_type=input_type if tag == "input" else tag,
                label=label_text or None,
                value=None,
            ))

        submit = await page.query_selector(
            f"{form_selector} button[type='submit'], "
            f"{form_selector} input[type='submit'], "
            f"{form_selector} button:not([type])"
        )
        submit_sel = None
        if submit:
            submit_id = await submit.get_attribute("id")
            if submit_id:
                submit_sel = f"#{submit_id}"
            else:
                submit_sel = f"{form_selector} [type='submit']"

        return FormDefinition(
            action_url=action,
            method=method,
            fields=fields,
            submit_selector=submit_sel,
        )

    async def fill_and_submit(
        self, page, form: FormDefinition, values: dict, screenshot_path: str | None = None
    ) -> SubmitResult:
        """Fill form fields and submit."""
        try:
            for field in form.fields:
                if field.selector in values:
                    await page.click(field.selector)
                    await asyncio.sleep(random.uniform(0.2, 0.6))
                    await page.fill(field.selector, values[field.selector])
                    await asyncio.sleep(random.uniform(0.4, 1.0))

            if screenshot_path:
                await page.screenshot(path=screenshot_path + "_before_submit.png", full_page=True)

            if form.submit_selector:
                await page.click(form.submit_selector)
                await page.wait_for_load_state("networkidle", timeout=15000)

            after_screenshot = None
            if screenshot_path:
                after_screenshot = screenshot_path + "_after_submit.png"
                await page.screenshot(path=after_screenshot, full_page=True)

            return SubmitResult(
                success=True,
                response_text=await page.content(),
                screenshot_path=after_screenshot,
                error=None,
            )
        except Exception as e:
            logger.exception("form.submit_error")
            return SubmitResult(
                success=False,
                response_text=None,
                screenshot_path=None,
                error=str(e),
            )
