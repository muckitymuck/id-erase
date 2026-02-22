# id-erase: Technical Design

| Field | Value |
|-------|-------|
| Version | 0.1.0 |
| Date | 2026-02-22 |
| Status | Draft |

---

## 1. System Architecture

```
                          ┌──────────────────────────┐
                          │     OpenClaw Gateway      │
                          │       (Node.js)           │
                          └────────────┬─────────────┘
                                       │
                          ┌────────────▼─────────────┐
                          │  erasure_plan Plugin      │
                          │    (TypeScript)           │
                          │                          │
                          │  Actions:                │
                          │  1. start    (POST)      │
                          │  2. status   (GET)       │
                          │  3. approve  (POST)      │
                          │  4. artifact_get (GET)   │
                          └────────────┬─────────────┘
                                       │ Bearer Token
                          ┌────────────▼─────────────┐
                          │  Erasure Executor         │
                          │  (Python / FastAPI)       │
                          │  Port: 8080              │
                          │                          │
                          │  ┌─────────────────────┐ │
                          │  │  DAG Runner          │ │
                          │  │  (from seo-fetch)    │ │
                          │  │  - Run claiming      │ │
                          │  │  - Task ordering     │ │
                          │  │  - Approval gates    │ │
                          │  │  - Idempotency       │ │
                          │  └─────────────────────┘ │
                          │                          │
                          │  ┌─────────────────────┐ │
                          │  │  Task Registry       │ │
                          │  │  - http.request      │ │
                          │  │  - scrape.static     │ │
                          │  │  - scrape.rendered   │ │
                          │  │  - form.submit       │ │
                          │  │  - email.send        │ │
                          │  │  - email.check       │ │
                          │  │  - email.click_verify│ │
                          │  │  - match.identity    │ │
                          │  │  - broker.update     │ │
                          │  │  - wait.delay        │ │
                          │  │  - llm.json          │ │
                          │  └─────────────────────┘ │
                          │                          │
                          │  ┌─────────────────────┐ │
                          │  │  Connectors          │ │
                          │  │  - HttpConnector     │ │
                          │  │  - BrowserConnector  │ │
                          │  │  - EmailConnector    │ │
                          │  │  - FormConnector     │ │
                          │  │  - ScrapeConnector   │ │
                          │  └─────────────────────┘ │
                          │                          │
                          │  ┌─────────────────────┐ │
                          │  │  PII Vault           │ │
                          │  │  (AES-256-GCM)       │ │
                          │  └─────────────────────┘ │
                          │                          │
                          │  ┌─────────────────────┐ │
                          │  │  Scheduler           │ │
                          │  │  (re-scan cron)      │ │
                          │  └─────────────────────┘ │
                          └────────────┬─────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
           ┌────────▼──────┐  ┌────────▼──────┐  ┌───────▼───────┐
           │  PostgreSQL   │  │  Email Server │  │  LLM API      │
           │  (state + PII)│  │  (IMAP/SMTP)  │  │  (OpenAI-     │
           │               │  │               │  │   compatible) │
           └───────────────┘  └───────────────┘  └───────────────┘
```

### 1.1 Component Responsibilities

| Component | Responsibility | Source |
|-----------|---------------|--------|
| OpenClaw Gateway | Agent runtime, tool dispatch, sandbox | Forked/controlled |
| erasure_plan Plugin | Bridge between OpenClaw and executor HTTP API | New (TypeScript) |
| Erasure Executor | Plan loading, DAG execution, task dispatch, approval gates | Forked from seo-executor |
| DAG Runner | Run claiming, task ordering, idempotency, retry, timeout | Reused from seo-fetch |
| Task Registry | Dispatch to connector by task type | Extended from seo-fetch |
| PII Vault | Encrypted storage and retrieval of user identity data | New |
| Scheduler | Cron-like recurring scan triggers | New |
| BrowserConnector | Playwright automation for JS-heavy sites | New |
| EmailConnector | IMAP/SMTP for agent email operations | New |
| FormConnector | Form detection and submission via Playwright | New |

---

## 2. Project Structure

```
id-erase/
├── .claude/
│   ├── PRD.md
│   ├── design.md              # This file
│   ├── roadmap.md
│   └── tasks.md
│
├── config/
│   ├── executor.config.yaml   # Executor runtime config
│   └── openclaw.openclaw.json5  # Agent + plugin config
│
├── packages/
│   ├── erasure-executor/      # Python FastAPI service
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   └── src/erasure_executor/
│   │       ├── main.py
│   │       ├── api.py         # REST endpoints
│   │       ├── auth.py        # Bearer token validation
│   │       ├── config.py      # Config loading
│   │       ├── logging.py     # JSON structured logging + PII redaction
│   │       ├── metrics.py     # Prometheus counters/histograms
│   │       │
│   │       ├── engine/
│   │       │   ├── runner.py      # DAG executor (from seo-fetch)
│   │       │   ├── plans.py       # Plan loader + validator (from seo-fetch)
│   │       │   ├── artifacts.py   # Artifact persistence (from seo-fetch)
│   │       │   ├── idempotency.py # Idempotency key handling (from seo-fetch)
│   │       │   ├── retries.py     # Retry policy (from seo-fetch)
│   │       │   ├── scheduler.py   # NEW: Recurring scan scheduler
│   │       │   └── pii_vault.py   # NEW: Encrypted PII storage
│   │       │
│   │       ├── connectors/
│   │       │   ├── http.py        # httpx client (from seo-fetch)
│   │       │   ├── scraper.py     # BeautifulSoup parser (extended)
│   │       │   ├── browser.py     # NEW: Playwright automation
│   │       │   ├── email.py       # NEW: IMAP/SMTP client
│   │       │   └── form.py        # NEW: Form detection + submission
│   │       │
│   │       ├── tasks/
│   │       │   └── registry.py    # Task type dispatch (extended)
│   │       │
│   │       ├── matching/
│   │       │   └── identity.py    # NEW: PII matching engine
│   │       │
│   │       ├── db/
│   │       │   ├── base.py
│   │       │   ├── session.py
│   │       │   ├── models.py      # ORM models (extended)
│   │       │   └── migrations/    # Alembic
│   │       │
│   │       ├── schemas/
│   │       │   ├── plan.py        # Plan Pydantic models
│   │       │   ├── models.py      # API request/response models
│   │       │   └── pii.py         # NEW: PII profile schema
│   │       │
│   │       └── utils/
│   │           ├── template.py    # {{ variable }} resolution
│   │           ├── json.py
│   │           └── redact.py      # NEW: PII redaction filter
│   │
│   └── openclaw-plugin-erasure/   # TypeScript OpenClaw plugin
│       ├── package.json
│       ├── tsconfig.json
│       ├── openclaw.plugin.json
│       ├── index.ts
│       └── src/
│           ├── schema.ts
│           ├── http.ts
│           ├── errors.ts
│           └── types.ts
│
├── workspace-template/
│   ├── IDENTITY.md
│   ├── SOUL.md
│   ├── AGENTS.md
│   ├── TOOLS.md
│   ├── BOOTSTRAP.md
│   └── plans/
│       └── brokers/               # One YAML plan per broker
│           ├── spokeo.yaml
│           ├── beenverified.yaml
│           ├── intelius.yaml
│           ├── whitepages.yaml
│           ├── familytreenow.yaml
│           ├── truepeoplesearch.yaml
│           ├── fastpeoplesearch.yaml
│           ├── radaris.yaml
│           ├── peoplefinder.yaml
│           └── acxiom.yaml
│
├── broker-catalog/
│   └── catalog.yaml               # Broker metadata registry
│
├── schemas/
│   ├── executor-config.schema.json
│   ├── erasure-plan.schema.json
│   └── pii-profile.schema.json
│
├── docker-compose.yml
├── Makefile
├── prelim-PRD.txt
└── prelim-design.md
```

---

## 3. Database Schema

### 3.1 Reused from seo-fetch

These tables are carried over with minimal changes:

```sql
-- Run execution records
CREATE TABLE runs (
    run_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id             TEXT NOT NULL,
    plan_hash           TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'queued',
        -- queued | running | blocked_for_approval | succeeded | failed
    requested_by        TEXT,
    idempotency_key     TEXT UNIQUE,
    params_json         JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    claimed_by          TEXT,
    claim_expires_at    TIMESTAMPTZ,
    error_code          TEXT,
    error_message       TEXT,
    result_summary_json JSONB
);

-- Per-task execution state
CREATE TABLE run_tasks (
    task_run_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID NOT NULL REFERENCES runs(run_id),
    task_id             TEXT NOT NULL,
    task_index          INT NOT NULL,
    task_name           TEXT,
    task_type           TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending',
        -- pending | running | succeeded | failed | skipped
    attempt             INT NOT NULL DEFAULT 0,
    max_attempts        INT NOT NULL DEFAULT 3,
    idempotent          BOOLEAN NOT NULL DEFAULT true,
    requires_approval   BOOLEAN NOT NULL DEFAULT false,
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    input_json          JSONB,
    output_json         JSONB,
    error_code          TEXT,
    error_message       TEXT
);

-- Approval gates
CREATE TABLE run_approvals (
    approval_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID NOT NULL REFERENCES runs(run_id),
    task_id             TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending',
        -- pending | approved | denied
    prompt              TEXT,
    preview_json        JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at         TIMESTAMPTZ,
    resolved_by         TEXT
);

-- Output storage references
CREATE TABLE run_artifacts (
    artifact_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID NOT NULL REFERENCES runs(run_id),
    kind                TEXT NOT NULL,
    content_type        TEXT,
    uri                 TEXT NOT NULL,
    metadata_json       JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 3.2 New Tables

```sql
-- Encrypted PII profile (single-user MVP; profile_id for future multi-user)
CREATE TABLE pii_profiles (
    profile_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label               TEXT NOT NULL DEFAULT 'default',
    encrypted_data      BYTEA NOT NULL,         -- AES-256-GCM encrypted JSON
    encryption_iv       BYTEA NOT NULL,          -- Initialization vector
    encryption_tag      BYTEA NOT NULL,          -- Authentication tag
    data_hash           TEXT NOT NULL,            -- SHA-256 of plaintext for change detection
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Broker listing discovery and tracking
CREATE TABLE broker_listings (
    listing_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    broker_id           TEXT NOT NULL,
    profile_id          UUID NOT NULL REFERENCES pii_profiles(profile_id),
    status              TEXT NOT NULL DEFAULT 'found',
        -- found | removal_submitted | pending_verification
        -- | removed | reappeared | manual_required | failed
    listing_url         TEXT,
    listing_snapshot     JSONB,                  -- extracted data from the listing
    matched_fields      JSONB,                   -- which PII fields matched
    confidence          FLOAT NOT NULL DEFAULT 0.0,
    discovered_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    removal_sent_at     TIMESTAMPTZ,
    verified_at         TIMESTAMPTZ,
    last_checked_at     TIMESTAMPTZ,
    recheck_after       TIMESTAMPTZ,             -- when to next re-scan
    notes               TEXT,

    CONSTRAINT valid_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0)
);
CREATE INDEX idx_broker_listings_broker ON broker_listings(broker_id);
CREATE INDEX idx_broker_listings_status ON broker_listings(status);
CREATE INDEX idx_broker_listings_recheck ON broker_listings(recheck_after)
    WHERE status NOT IN ('removed');

-- Individual removal actions taken
CREATE TABLE removal_actions (
    action_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id          UUID NOT NULL REFERENCES broker_listings(listing_id),
    run_id              UUID REFERENCES runs(run_id),
    action_type         TEXT NOT NULL,
        -- form_submit | email_optout | api_call
        -- | email_verification | manual_queue
    request_summary     TEXT,                    -- human-readable description (redacted)
    response_status     TEXT,
    confirmation_id     TEXT,
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_removal_actions_listing ON removal_actions(listing_id);

-- Human action queue for things the agent can't do
CREATE TABLE human_action_queue (
    queue_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id          UUID REFERENCES broker_listings(listing_id),
    broker_id           TEXT NOT NULL,
    action_needed       TEXT NOT NULL,
    instructions        TEXT,                    -- step-by-step for the human
    priority            INT NOT NULL DEFAULT 0,  -- higher = more urgent
    status              TEXT NOT NULL DEFAULT 'pending',
        -- pending | completed | skipped
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    completed_notes     TEXT
);
CREATE INDEX idx_human_queue_status ON human_action_queue(status)
    WHERE status = 'pending';

-- Scheduled scan jobs
CREATE TABLE scan_schedule (
    schedule_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    broker_id           TEXT NOT NULL,
    profile_id          UUID NOT NULL REFERENCES pii_profiles(profile_id),
    scan_type           TEXT NOT NULL DEFAULT 'discovery',
        -- discovery | verification | re_check
    next_run_at         TIMESTAMPTZ NOT NULL,
    last_run_id         UUID REFERENCES runs(run_id),
    last_run_at         TIMESTAMPTZ,
    interval_days       INT NOT NULL DEFAULT 30,
    enabled             BOOLEAN NOT NULL DEFAULT true,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_scan_schedule_next ON scan_schedule(next_run_at)
    WHERE enabled = true;
```

---

## 4. Connectors (Detailed)

### 4.1 BrowserConnector (Playwright)

The most critical new connector. Most data brokers render content with JavaScript and use anti-bot measures.

```python
# connectors/browser.py

import asyncio
import random
from dataclasses import dataclass
from playwright.async_api import async_playwright, Page, Browser

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ...",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ...",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ...",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
]


@dataclass
class BrowserResult:
    url: str
    status: int
    html: str
    screenshot_path: str | None
    extracted: dict | None


class BrowserConnector:
    """Playwright-based browser for JS-heavy broker sites."""

    def __init__(self, headless: bool = True, stealth: bool = True):
        self._headless = headless
        self._stealth = stealth
        self._browser: Browser | None = None

    async def _get_browser(self) -> Browser:
        if self._browser is None:
            pw = await async_playwright().start()
            self._browser = await pw.chromium.launch(headless=self._headless)
        return self._browser

    async def _new_page(self) -> Page:
        browser = await self._get_browser()
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport=random.choice(VIEWPORTS),
            locale="en-US",
        )
        page = await context.new_page()
        return page

    async def navigate(self, url: str, wait_for: str | None = None) -> Page:
        page = await self._new_page()
        await page.goto(url, wait_until="networkidle")
        if wait_for:
            await page.wait_for_selector(wait_for, timeout=15000)
        # Human-like delay
        await asyncio.sleep(random.uniform(1.0, 3.0))
        return page

    async def extract(self, page: Page, selectors: dict) -> dict:
        """Extract data from page using CSS selectors."""
        results = {}
        for key, selector in selectors.items():
            if " @" in selector:
                css, attr = selector.rsplit(" @", 1)
                elements = await page.query_selector_all(css)
                results[key] = [
                    await el.get_attribute(attr) for el in elements
                ]
            else:
                elements = await page.query_selector_all(selector)
                results[key] = [
                    await el.text_content() for el in elements
                ]
        return results

    async def fill_form(self, page: Page, fields: list[dict]) -> None:
        """Fill form fields with human-like delays."""
        for field in fields:
            selector = field["selector"]
            value = field["value"]
            await page.click(selector)
            await asyncio.sleep(random.uniform(0.3, 0.8))
            await page.fill(selector, value)
            await asyncio.sleep(random.uniform(0.5, 1.5))

    async def click_and_wait(self, page: Page, selector: str,
                              wait_for: str | None = None) -> None:
        await page.click(selector)
        if wait_for:
            await page.wait_for_selector(wait_for, timeout=15000)
        await asyncio.sleep(random.uniform(1.0, 3.0))

    async def screenshot(self, page: Page, path: str) -> str:
        await page.screenshot(path=path, full_page=True)
        return path

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
```

### 4.2 EmailConnector

```python
# connectors/email.py

import email
import imaplib
import re
import smtplib
import time
from dataclasses import dataclass
from email.mime.text import MIMEText


@dataclass
class EmailMessage:
    message_id: str
    from_addr: str
    subject: str
    body: str
    html: str | None
    received_at: str
    links: list[str]


@dataclass
class EmailConfig:
    address: str
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int
    password: str
    alternative_addresses: list[str]


class EmailConnector:
    """IMAP/SMTP client for the agent's dedicated email."""

    def __init__(self, config: EmailConfig):
        self._config = config

    def send(self, to: str, subject: str, body: str,
             from_addr: str | None = None) -> dict:
        """Send an email from the agent's address."""
        sender = from_addr or self._config.address
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to

        with smtplib.SMTP(self._config.smtp_host, self._config.smtp_port) as smtp:
            smtp.starttls()
            smtp.login(self._config.address, self._config.password)
            smtp.send_message(msg)

        return {"status": "sent", "to": to, "subject": subject}

    def check_inbox(self, from_filter: str | None = None,
                    subject_filter: str | None = None,
                    since_minutes: int = 60,
                    wait_minutes: int = 0,
                    poll_interval_seconds: int = 30) -> list[EmailMessage]:
        """Poll inbox for matching emails."""
        deadline = time.time() + (wait_minutes * 60)

        while True:
            results = self._search_inbox(from_filter, subject_filter)
            if results:
                return results
            if time.time() >= deadline:
                return []
            time.sleep(poll_interval_seconds)

    def _search_inbox(self, from_filter: str | None,
                      subject_filter: str | None) -> list[EmailMessage]:
        with imaplib.IMAP4_SSL(self._config.imap_host,
                                self._config.imap_port) as imap:
            imap.login(self._config.address, self._config.password)
            imap.select("INBOX")

            criteria = []
            if from_filter:
                criteria.append(f'FROM "{from_filter}"')
            if subject_filter:
                criteria.append(f'SUBJECT "{subject_filter}"')

            search_str = " ".join(criteria) if criteria else "ALL"
            _, message_ids = imap.search(None, search_str)

            messages = []
            for mid in message_ids[0].split():
                _, data = imap.fetch(mid, "(RFC822)")
                raw = email.message_from_bytes(data[0][1])
                body = self._get_body(raw)
                html = self._get_html(raw)
                links = self._extract_links(body + (html or ""))

                messages.append(EmailMessage(
                    message_id=raw["Message-ID"] or "",
                    from_addr=raw["From"] or "",
                    subject=raw["Subject"] or "",
                    body=body,
                    html=html,
                    received_at=raw["Date"] or "",
                    links=links,
                ))

            return messages

    @staticmethod
    def _get_body(msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    return part.get_payload(decode=True).decode("utf-8", errors="replace")
        return msg.get_payload(decode=True).decode("utf-8", errors="replace")

    @staticmethod
    def _get_html(msg) -> str | None:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    return part.get_payload(decode=True).decode("utf-8", errors="replace")
        return None

    @staticmethod
    def _extract_links(text: str) -> list[str]:
        return re.findall(r'https?://[^\s<>"\']+', text)
```

### 4.3 FormConnector

```python
# connectors/form.py

from dataclasses import dataclass
from playwright.async_api import Page


@dataclass
class FormField:
    selector: str
    field_type: str      # text | email | select | checkbox | radio
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

    async def detect_form(self, page: Page,
                          hints: dict | None = None) -> FormDefinition | None:
        """Find the opt-out form on the page using hints or heuristics."""
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
                                          "delete", "privacy"]):
                return await self._parse_form(page, f"form:nth-of-type({i+1})")

        return None

    async def _parse_form(self, page: Page,
                           form_selector: str) -> FormDefinition:
        form = await page.query_selector(form_selector)
        action = await form.get_attribute("action") if form else None
        method = (await form.get_attribute("method") or "POST").upper() if form else "POST"

        fields = []
        inputs = await page.query_selector_all(f"{form_selector} input, "
                                                f"{form_selector} select, "
                                                f"{form_selector} textarea")
        for inp in inputs:
            tag = await inp.evaluate("el => el.tagName.toLowerCase()")
            input_type = await inp.get_attribute("type") or "text"
            name = await inp.get_attribute("name")
            label_text = await inp.evaluate(
                "el => el.labels?.[0]?.textContent?.trim() || "
                "el.getAttribute('placeholder') || "
                "el.getAttribute('aria-label') || ''"
            )
            fields.append(FormField(
                selector=f"[name='{name}']" if name else "",
                field_type=input_type if tag == "input" else tag,
                label=label_text,
                value=None,
            ))

        submit = await page.query_selector(
            f"{form_selector} button[type='submit'], "
            f"{form_selector} input[type='submit']"
        )
        submit_sel = None
        if submit:
            submit_id = await submit.get_attribute("id")
            submit_sel = f"#{submit_id}" if submit_id else f"{form_selector} [type='submit']"

        return FormDefinition(
            action_url=action,
            method=method,
            fields=fields,
            submit_selector=submit_sel,
        )

    async def fill_and_submit(self, page: Page, form: FormDefinition,
                               values: dict,
                               browser_connector=None) -> SubmitResult:
        """Fill form fields and submit."""
        try:
            fill_fields = []
            for field in form.fields:
                if field.selector and field.selector in values:
                    fill_fields.append({
                        "selector": field.selector,
                        "value": values[field.selector],
                    })

            if browser_connector:
                await browser_connector.fill_form(page, fill_fields)

            if form.submit_selector:
                await page.click(form.submit_selector)
                await page.wait_for_load_state("networkidle")

            return SubmitResult(
                success=True,
                response_text=await page.content(),
                screenshot_path=None,
                error=None,
            )
        except Exception as e:
            return SubmitResult(
                success=False,
                response_text=None,
                screenshot_path=None,
                error=str(e),
            )
```

---

## 5. Identity Matching Engine

The matching engine determines whether a scraped broker listing belongs to the user.

### 5.1 Two-Stage Matching

**Stage 1: Heuristic scoring** — fast, no LLM cost

```python
# matching/identity.py

@dataclass
class MatchResult:
    listing_index: int
    confidence: float
    matched_fields: dict[str, bool]
    reasoning: str


def heuristic_match(listing: dict, profile: dict) -> MatchResult:
    """Score a listing against the PII profile using field comparison."""
    score = 0.0
    total_weight = 0.0
    matched = {}

    # Name match (weight: 0.3)
    if "name" in listing:
        total_weight += 0.3
        listing_name = normalize_name(listing["name"])
        profile_names = [normalize_name(profile["full_name"])]
        profile_names += [normalize_name(a) for a in profile.get("aliases", [])]
        if any(names_match(listing_name, pn) for pn in profile_names):
            score += 0.3
            matched["name"] = True

    # Location match (weight: 0.25)
    if "location" in listing:
        total_weight += 0.25
        if location_matches(listing["location"], profile.get("addresses", [])):
            score += 0.25
            matched["location"] = True

    # Age match (weight: 0.2)
    if "age" in listing and "date_of_birth" in profile:
        total_weight += 0.2
        if age_matches(listing["age"], profile["date_of_birth"], tolerance=2):
            score += 0.2
            matched["age"] = True

    # Relatives match (weight: 0.15)
    if "relatives" in listing:
        total_weight += 0.15
        if relatives_match(listing["relatives"], profile.get("relatives", [])):
            score += 0.15
            matched["relatives"] = True

    # Phone match (weight: 0.1)
    if "phone" in listing:
        total_weight += 0.1
        if phone_matches(listing["phone"], profile.get("phone_numbers", [])):
            score += 0.1
            matched["phone"] = True

    confidence = score / total_weight if total_weight > 0 else 0.0

    return MatchResult(
        listing_index=0,
        confidence=confidence,
        matched_fields=matched,
        reasoning=f"Matched {len(matched)}/{int(total_weight/0.1)} fields",
    )
```

**Stage 2: LLM verification** — for borderline cases (confidence 0.4-0.8)

```python
def llm_verify_match(listing: dict, profile: dict,
                     heuristic_result: MatchResult,
                     llm_connector) -> MatchResult:
    """Use LLM to verify ambiguous matches."""
    # Only invoke LLM for borderline confidence
    if heuristic_result.confidence >= 0.8 or heuristic_result.confidence < 0.4:
        return heuristic_result

    prompt = (
        "Compare this data broker listing against the user's profile. "
        "Determine if they are the same person. Consider name variations, "
        "address history, and age consistency. Return a JSON object with "
        "'is_match' (boolean), 'confidence' (0.0-1.0), and 'reasoning' (string)."
    )
    # LLM receives redacted/minimal data — only fields needed for comparison
    # Full PII is never sent; only matched field values
    ...
```

### 5.2 Confidence Thresholds

| Confidence | Action |
|-----------|--------|
| >= 0.8 | Auto-proceed to removal (with approval gate) |
| 0.4 - 0.8 | LLM verification, then human review if still uncertain |
| < 0.4 | Skip — likely not the user |

---

## 6. Task Type Specifications

### 6.1 scrape.rendered

Renders a page with Playwright and extracts data.

```yaml
# Plan usage
- id: search_listing
  type: scrape.rendered
  input:
    target_id: spokeo
    url_template: "/search?q={{params.full_name}}"
    wait_for: ".search-results"          # CSS selector to wait for
    extract:
      listings: ".result-item"           # container selector
      fields:
        name: ".result-name"
        location: ".result-location"
        age: ".result-age"
        link: ".result-link @href"       # @attr extracts attribute
    screenshot: true                      # save screenshot as artifact
```

### 6.2 form.submit

Detects and fills an opt-out form.

```yaml
- id: submit_optout
  type: form.submit
  input:
    target_id: spokeo
    url_template: "/optout"
    form_hints:
      form_selector: "#optout-form"
    values:
      "[name='url']": "{{state.matched_listings.listings[0].url}}"
      "[name='email']": "{{agent_email}}"
    screenshot: true
```

### 6.3 email.send

Sends an email from the agent's address.

```yaml
- id: send_optout_email
  type: email.send
  input:
    to: "privacy@broker.com"
    subject: "Data Removal Request"
    body_template: |
      I am writing to request the removal of my personal information
      from your database. The listing URL is: {{state.listing_url}}
      Please confirm removal at your earliest convenience.
```

### 6.4 email.check

Polls inbox for matching emails.

```yaml
- id: check_verification
  type: email.check
  input:
    wait_minutes: 30
    poll_interval_seconds: 60
    from_filter: "noreply@spokeo.com"
    subject_filter: "verify"
    extract_links: true
```

### 6.5 email.click_verify

Opens a verification link in the browser.

```yaml
- id: click_verify
  type: email.click_verify
  input:
    link_ref: "state.verification_email.links[0]"
    wait_for: ".confirmation-message"
    screenshot: true
```

### 6.6 match.identity

Runs the identity matching engine against scraped listings.

```yaml
- id: match_results
  type: match.identity
  input:
    listings_ref: search_results
    match_fields: [name, location, age, relatives]
    confidence_threshold: 0.8
    llm_verify_borderline: true
```

### 6.7 broker.update_status

Updates the broker_listings table.

```yaml
- id: update_status
  type: broker.update_status
  input:
    broker_id: spokeo
    status: pending_verification
    listing_ref: matched_listings
    recheck_days: 7
```

### 6.8 wait.delay

Pauses plan execution (for verification wait periods).

```yaml
- id: wait_for_processing
  type: wait.delay
  input:
    hours: 48
    reason: "Wait for broker to process removal request"
```

---

## 7. PII Vault

### 7.1 Encryption Design

```python
# engine/pii_vault.py

import hashlib
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class PIIVault:
    """Encrypted storage for PII profiles."""

    def __init__(self, encryption_key: bytes):
        """Key must be 32 bytes (256-bit) for AES-256-GCM.

        Derive from env var or user passphrase:
            key = hashlib.pbkdf2_hmac('sha256', passphrase, salt, 100000)
        """
        if len(encryption_key) != 32:
            raise ValueError("Encryption key must be 32 bytes")
        self._aesgcm = AESGCM(encryption_key)

    def encrypt(self, profile_data: dict) -> tuple[bytes, bytes, bytes]:
        """Returns (ciphertext, iv, tag). Tag is appended to ciphertext by AESGCM."""
        plaintext = json.dumps(profile_data, ensure_ascii=False).encode("utf-8")
        iv = os.urandom(12)  # 96-bit nonce
        ciphertext = self._aesgcm.encrypt(iv, plaintext, None)
        # AESGCM appends the 16-byte tag to ciphertext
        ct = ciphertext[:-16]
        tag = ciphertext[-16:]
        return ct, iv, tag

    def decrypt(self, ciphertext: bytes, iv: bytes, tag: bytes) -> dict:
        """Decrypt and return PII profile dict."""
        combined = ciphertext + tag
        plaintext = self._aesgcm.decrypt(iv, combined, None)
        return json.loads(plaintext.decode("utf-8"))

    @staticmethod
    def data_hash(profile_data: dict) -> str:
        """SHA-256 hash for change detection without decryption."""
        canonical = json.dumps(profile_data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

### 7.2 PII Redaction Filter

```python
# utils/redact.py

import re
import logging


class RedactingFilter(logging.Filter):
    """Strips PII patterns from log records."""

    PATTERNS = [
        (re.compile(r'\b\d{3}[-.]?\d{2}[-.]?\d{4}\b'), '[SSN-REDACTED]'),
        (re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'), '[PHONE-REDACTED]'),
        (re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'), '[EMAIL-REDACTED]'),
        (re.compile(r'\b\d{5}(?:-\d{4})?\b'), '[ZIP-REDACTED]'),
    ]

    def __init__(self, additional_terms: list[str] | None = None):
        super().__init__()
        self._additional = additional_terms or []

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern, replacement in self.PATTERNS:
            msg = pattern.sub(replacement, msg)
        for term in self._additional:
            if term and len(term) > 2:
                msg = msg.replace(term, '[PII-REDACTED]')
        record.msg = msg
        record.args = ()
        return True
```

---

## 8. Scheduler Design

```python
# engine/scheduler.py

from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from sqlalchemy.orm import Session

from erasure_executor.db.models import ScanSchedule, BrokerListing


@dataclass
class ScanJob:
    schedule_id: str
    broker_id: str
    profile_id: str
    scan_type: str          # discovery | verification | re_check
    plan_id: str


class ErasureScheduler:
    """Triggers broker scans based on configurable intervals."""

    def __init__(self, db: Session, broker_catalog: dict):
        self._db = db
        self._catalog = broker_catalog

    def get_due_jobs(self) -> list[ScanJob]:
        """Return scan jobs where next_run_at <= now."""
        now = datetime.now(timezone.utc)
        schedules = (
            self._db.query(ScanSchedule)
            .filter(ScanSchedule.enabled == True)
            .filter(ScanSchedule.next_run_at <= now)
            .order_by(ScanSchedule.next_run_at)
            .all()
        )
        jobs = []
        for s in schedules:
            broker = self._catalog.get(s.broker_id)
            if broker and broker.get("plan_file"):
                jobs.append(ScanJob(
                    schedule_id=str(s.schedule_id),
                    broker_id=s.broker_id,
                    profile_id=str(s.profile_id),
                    scan_type=s.scan_type,
                    plan_id=f"broker_{s.broker_id}",
                ))
        return jobs

    def mark_started(self, schedule_id: str, run_id: str) -> None:
        """Record that a scan was started and advance next_run_at."""
        schedule = self._db.get(ScanSchedule, schedule_id)
        if schedule:
            schedule.last_run_id = run_id
            schedule.last_run_at = datetime.now(timezone.utc)
            schedule.next_run_at = (
                datetime.now(timezone.utc)
                + timedelta(days=schedule.interval_days)
            )
            self._db.commit()

    def initialize_for_profile(self, profile_id: str) -> None:
        """Create scan schedules for all brokers in the catalog."""
        now = datetime.now(timezone.utc)
        for broker_id, broker in self._catalog.items():
            if not broker.get("plan_file"):
                continue
            existing = (
                self._db.query(ScanSchedule)
                .filter_by(broker_id=broker_id, profile_id=profile_id)
                .first()
            )
            if not existing:
                schedule = ScanSchedule(
                    broker_id=broker_id,
                    profile_id=profile_id,
                    scan_type="discovery",
                    next_run_at=now,
                    interval_days=broker.get("recheck_days", 30),
                    enabled=True,
                )
                self._db.add(schedule)
        self._db.commit()
```

---

## 9. Configuration

### 9.1 Executor Config

```yaml
# config/executor.config.yaml
bind_host: "0.0.0.0"
bind_port: 8080

auth_token: "env:EXECUTOR_TOKEN"
database_url: "env:DATABASE_URL"
plans_root: "/plans"
artifacts_root: "/artifacts"

max_concurrent_runs: 4
default_timeout_ms: 120000       # 2 min per task (browser tasks are slow)
run_timeout_ms: 3600000          # 60 min max run time (email waits)
run_claim_ttl_seconds: 300

retry:
  attempts: 3
  min_delay_ms: 500
  max_delay_ms: 60000
  jitter: 0.15

policy:
  require_idempotency_key: true
  fail_closed_on_missing_policy: true
  side_effects_require_approval: true
  allow_shell: false
  allowed_binaries: []
  confidence_threshold: 0.8       # auto-proceed above this
  require_approval_first_broker: true  # always approve first time per broker

pii:
  encryption_key: "env:PII_ENCRYPTION_KEY"   # 32-byte hex or base64
  log_redaction: true
  artifact_retention:
    html_days: 7
    screenshot_days: 30
    confirmation_days: -1          # keep forever

agent_email:
  address: "env:AGENT_EMAIL_ADDRESS"
  imap_host: "env:AGENT_EMAIL_IMAP_HOST"
  imap_port: 993
  smtp_host: "env:AGENT_EMAIL_SMTP_HOST"
  smtp_port: 587
  password: "env:AGENT_EMAIL_PASSWORD"
  alternative_addresses: []

browser:
  headless: true
  stealth: true
  default_timeout_ms: 15000

scheduler:
  enabled: true
  poll_interval_seconds: 300      # check for due jobs every 5 min

llm:
  provider: "mock"
  endpoint: "env:LLM_ENDPOINT"
  api_key: "env:LLM_API_KEY"
  model: "env:LLM_MODEL"
```

### 9.2 OpenClaw Agent Config

```json5
// config/openclaw.openclaw.json5
{
  agents: {
    defaults: { workspace: "~/.openclaw/workspace", maxConcurrent: 1 },
    list: [{
      id: "erasure",
      default: true,
      sandbox: {
        mode: "all",
        scope: "session",
        workspaceAccess: "none",
        docker: { network: "none" }
      },
      tools: {
        profile: "messaging",
        allow: ["erasure_plan"],
        deny: ["group:runtime", "group:fs", "browser", "web_search", "web_fetch"]
      }
    }]
  },
  plugins: {
    enabled: true,
    entries: {
      "erasure-plan": {
        config: {
          executorBaseUrl: "http://erasure-executor:8080",
          executorToken: "env:EXECUTOR_TOKEN",
          plansRoot: "/plans"
        }
      }
    }
  }
}
```

### 9.3 Docker Compose (Local Dev)

```yaml
# docker-compose.yml
version: "3.9"

services:
  erasure-executor:
    build: ./packages/erasure-executor
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgresql+psycopg://erasure:erasure@postgres:5432/erasure
      EXECUTOR_TOKEN: dev-token-change-me
      PII_ENCRYPTION_KEY: "0000000000000000000000000000000000000000000000000000000000000000"
      AGENT_EMAIL_ADDRESS: "agent@localhost"
      AGENT_EMAIL_IMAP_HOST: "mailhog"
      AGENT_EMAIL_IMAP_PORT: "1143"
      AGENT_EMAIL_SMTP_HOST: "mailhog"
      AGENT_EMAIL_SMTP_PORT: "1025"
      AGENT_EMAIL_PASSWORD: ""
      LLM_ENDPOINT: ""
      LLM_API_KEY: ""
      LLM_MODEL: ""
    volumes:
      - artifacts:/artifacts
    depends_on:
      - postgres
      - mailhog

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: erasure
      POSTGRES_PASSWORD: erasure
      POSTGRES_DB: erasure
    ports:
      - "5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data

  mailhog:
    image: mailhog/mailhog:latest
    ports:
      - "8025:8025"   # Web UI
      - "1025:1025"   # SMTP
      - "1143:1143"   # IMAP (if supported)

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./config/prometheus.yml:/etc/prometheus/prometheus.yml

volumes:
  pg_data:
  artifacts:
```

---

## 10. Broker Plan Schema

All broker YAML plans follow this schema:

```yaml
# Required fields
plan_id: string             # unique identifier, e.g. "broker_spokeo"
version: semver             # e.g. "1.0.0"
description: string         # human-readable description
owner: string               # "id-erase"
labels: [string]            # categorization tags

# Target sites
targets:
  - target_id: string       # reference ID used in tasks
    kind: string             # "website" | "api" | "email"
    base_url: string         # e.g. "https://www.spokeo.com"
    notes: string            # optional notes

# Runtime parameters (populated from PII profile)
params_schema:
  type: object
  properties:
    full_name: { type: string }
    city: { type: string }
    state: { type: string }
    email: { type: string }
    # ... varies by broker
  required: [full_name]

# Task DAG
tasks:
  - id: string              # unique within plan
    name: string             # human-readable
    type: string             # task type from registry
    depends_on: [string]     # task IDs that must complete first
    requires_approval: bool  # if true, blocks for human decision
    approval:                # only if requires_approval
      prompt: string         # what to show the human
      preview_kind: string   # "json" | "text" | "screenshot"
    input: object            # task-type-specific input
    output:
      save_as: string        # state key for downstream tasks
      artifact_kind: string  # artifact classification
```

---

## 11. API Endpoints

### 11.1 Executor API (reused from seo-fetch)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v1/runs` | Start a new broker plan run |
| GET | `/v1/runs/{run_id}` | Get run status + task states |
| POST | `/v1/runs/{run_id}/approvals/{approval_id}` | Approve or deny a gated action |
| GET | `/v1/runs/{run_id}/artifacts/{artifact_id}` | Fetch artifact content |
| GET | `/healthz` | Health check |
| GET | `/metrics` | Prometheus metrics |

### 11.2 New Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v1/profiles` | Create/update PII profile |
| GET | `/v1/profiles/{profile_id}` | Get profile metadata (no PII in response) |
| DELETE | `/v1/profiles/{profile_id}` | Delete profile and all associated data |
| GET | `/v1/brokers` | List all brokers from catalog with current status |
| GET | `/v1/brokers/{broker_id}/listings` | List all listings for a broker |
| GET | `/v1/queue` | List pending human action items |
| POST | `/v1/queue/{queue_id}/complete` | Mark a human action as done |
| GET | `/v1/schedule` | List upcoming scheduled scans |
| POST | `/v1/schedule/{schedule_id}/trigger` | Trigger a scan immediately |

---

## 12. Worked Example: Spokeo Removal Flow

### Step 1: User creates PII profile

```bash
curl -X POST http://localhost:8080/v1/profiles \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Jane Doe",
    "aliases": ["Jane M Doe"],
    "date_of_birth": "1985-03-15",
    "addresses": [{"street": "123 Main St", "city": "Chicago", "state": "IL", "zip": "60601", "current": true}],
    "phone_numbers": [{"number": "+13125551234", "type": "mobile"}],
    "email_addresses": ["jane.doe@example.com"]
  }'
```

### Step 2: Agent starts Spokeo discovery plan

```
erasure_plan(action="start", plan_id="broker_spokeo",
             params={"full_name": "Jane Doe", "city": "Chicago", "state": "IL"},
             idempotency_key="spokeo-jane-2026-02-22")
```

### Step 3: Executor runs DAG

```
[search_listing] → Playwright navigates to spokeo.com/search?q=Jane+Doe&l=Chicago+IL
                  → Waits for .search-results
                  → Extracts listings: [{name: "Jane M Doe", location: "Chicago, IL", age: "40", link: "/Jane-Doe/Chicago-IL/abc123"}]
                  → Saves screenshot as artifact

[match_results]  → Heuristic match: name=0.3 + location=0.25 + age=0.2 = 0.75/0.75 = 1.0
                 → Confidence 1.0, auto-proceed

[submit_optout]  → BLOCKED: requires_approval=true
                 → Preview: "Found 1 listing on Spokeo for Jane M Doe, Chicago IL. Submit opt-out?"
```

### Step 4: Agent presents approval to operator

```
Agent: "I found 1 listing for you on Spokeo:
        - Jane M Doe, age 40, Chicago, IL (confidence: 1.0)
        Shall I submit an opt-out request?"

Operator: "Yes, approve."
```

### Step 5: Agent approves, execution resumes

```
erasure_plan(action="approve", run_id="...", approval_id="...", decision="approve")

[submit_optout]  → Playwright navigates to spokeo.com/optout
                 → Fills listing URL + agent email
                 → Clicks submit
                 → Screenshot saved

[check_verification_email] → Polls agent inbox for 30 min
                           → Found email from noreply@spokeo.com: "Click to verify opt-out"
                           → Extracts verification link

[click_verify_link] → Playwright opens verification link
                    → Confirmation page: "Your opt-out request has been processed"
                    → Screenshot saved

[update_status] → broker_listings: status=pending_verification, recheck_after=+7 days
```

### Step 6: Scheduled re-check (7 days later)

Scheduler triggers a verification run. Agent searches Spokeo again for Jane Doe.
- If listing is gone → status=removed, next recheck in 30 days
- If listing is still there → status=reappeared, re-submit opt-out
