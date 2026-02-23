# id-erase: Task Tracker

| Field | Value |
|-------|-------|
| Version | 0.1.0 |
| Date | 2026-02-22 |
| Status | Phase 3 Complete |
| Tests | 165 passing (unit) |
| Next | Phase 4: CLI & Observability |

### Progress Summary

| Phase | Status | Key Deliverables |
|-------|--------|-----------------|
| 0. Foundation | Done | Executor fork, DB schema (5 tables), PII vault (AES-256-GCM), browser/email connectors, Docker Compose |
| 1. First Broker | Done | Identity matching engine (rapidfuzz), 7 task types implemented, Spokeo end-to-end plan, broker catalog |
| 2. Broker Expansion | Done | 10 broker YAML plans, scheduler daemon, human action queue, catalog-backed API |
| 3. Hardening | Done | Proxy/stealth, robots.txt, rate limiter, captcha.solve, artifact cleanup, dead letter tracker, plan health check |
| 4. CLI & Observability | Not started | CLI tool, Grafana dashboard, alerting |
| 5. Legal & Discovery | Future | CCPA/GDPR templates, search engine discovery |
| 6. Multi-User & Web UI | Future | JWT auth, web dashboard, Kubernetes |

### Deferred / Integration Test Backlog

These items require Docker (Playwright, PostgreSQL, MailHog) and are deferred to a dedicated integration test pass:

- [ ] Browser connector integration tests (navigate, extract, form fill, screenshot)
- [ ] Email connector integration tests (send via MailHog, check_inbox, extract links)
- [ ] scrape.rendered Playwright error handling (timeout, selector-not-found, navigation failure)
- [ ] form.submit integration tests with local HTML fixture
- [ ] broker.update_status DB integration tests (insert, status transitions, recheck_after)
- [ ] Docker Compose smoke test (`make build && make up && make migrate && healthz`)
- [ ] End-to-end Spokeo test against live site
- [ ] JSON schemas: executor-config, erasure-plan, pii-profile

---

## Phase 0: Foundation (Week 1-2)

### 0.1 Fork seo-executor → erasure-executor

- [x] Copy `seo-fetch/packages/seo-executor/` to `id-erase/packages/erasure-executor/`
- [x] Rename all `seo_executor` references to `erasure_executor` (module names, imports, pyproject.toml)
- [x] Update `pyproject.toml`:
  - Name: `erasure-executor`
  - Add dependencies: `playwright>=1.50.0`, `cryptography>=44.0.0`
  - Keep: `fastapi`, `uvicorn`, `pydantic`, `sqlalchemy`, `psycopg[binary]`, `alembic`, `prometheus-client`, `httpx`, `beautifulsoup4`, `lxml`, `jsonschema`, `PyYAML`
  - Remove: `GitPython` (not needed for MVP)
- [x] Remove SEO-specific code from `connectors/scraper.py` (keep BeautifulSoup util, remove SEO field extraction)
- [x] Remove `connectors/git.py` and `connectors/shell.py` (not needed for MVP)
- [x] Remove `git.apply_patch` and `shell.exec` from task registry
- [x] Verify all existing tests pass under new module paths
- [x] Create `Dockerfile` (Python 3.11, non-root user, Playwright browser deps)

### 0.2 Database schema

- [x] Create Alembic migration: `pii_profiles` table
  - Fields: profile_id (UUID PK), label, encrypted_data (BYTEA), encryption_iv (BYTEA), encryption_tag (BYTEA), data_hash, created_at, updated_at
- [x] Create Alembic migration: `broker_listings` table
  - Fields: listing_id (UUID PK), broker_id, profile_id (FK), status, listing_url, listing_snapshot (JSONB), matched_fields (JSONB), confidence, discovered_at, removal_sent_at, verified_at, last_checked_at, recheck_after, notes
  - Indexes: broker_id, status, recheck_after (partial WHERE status != 'removed')
  - Constraint: confidence CHECK (0.0-1.0)
- [x] Create Alembic migration: `removal_actions` table
  - Fields: action_id (UUID PK), listing_id (FK), run_id (FK), action_type, request_summary, response_status, confirmation_id, error_message, created_at
  - Index: listing_id
- [x] Create Alembic migration: `human_action_queue` table
  - Fields: queue_id (UUID PK), listing_id (FK), broker_id, action_needed, instructions, priority, status, created_at, completed_at, completed_notes
  - Index: status (partial WHERE status = 'pending')
- [x] Create Alembic migration: `scan_schedule` table
  - Fields: schedule_id (UUID PK), broker_id, profile_id (FK), scan_type, next_run_at, last_run_id (FK), last_run_at, interval_days, enabled, created_at
  - Index: next_run_at (partial WHERE enabled = true)
- [x] Add SQLAlchemy ORM models in `db/models.py` for all 5 new tables
- [x] Verify migrations run cleanly: `alembic upgrade head`

### 0.3 PII vault

- [x] Create `engine/pii_vault.py` — PIIVault class
  - `__init__(encryption_key: bytes)` — validate 32-byte key
  - `encrypt(profile_data: dict) -> tuple[bytes, bytes, bytes]` — AES-256-GCM
  - `decrypt(ciphertext, iv, tag) -> dict`
  - `data_hash(profile_data: dict) -> str` — SHA-256
- [x] Create `schemas/pii.py` — Pydantic models
  - `PIIProfile`: full_name, aliases, date_of_birth, addresses, phone_numbers, email_addresses, relatives
  - `PIIAddress`: street, city, state, zip, current
  - `PIIPhone`: number, type
  - `CreateProfileRequest`, `ProfileMetadataResponse`
- [x] Add API endpoints in `api.py`:
  - `POST /v1/profiles` — validate, encrypt, store
  - `GET /v1/profiles/{profile_id}` — return metadata only (label, data_hash, timestamps)
  - `DELETE /v1/profiles/{profile_id}` — delete profile + all associated broker_listings, removal_actions, scan_schedule
- [x] Add `PII_ENCRYPTION_KEY` to config loading (`config.py`)
- [x] Write tests:
  - Encrypt → decrypt round-trip produces identical data
  - Wrong key fails decryption
  - Key length validation
  - data_hash is deterministic
  - API create → get → delete lifecycle (unit tests; integration deferred)
  - DELETE cascades to related tables (integration deferred)

### 0.4 Browser connector

- [x] Create `connectors/browser.py` — BrowserConnector class
  - `navigate(url, wait_for) -> Page`
  - `extract(page, selectors) -> dict`
  - `fill_form(page, fields) -> None`
  - `click_and_wait(page, selector, wait_for) -> None`
  - `screenshot(page, path) -> str`
  - `close() -> None`
- [x] Stealth basics:
  - Randomized User-Agent from list of 5+ real browsers
  - Randomized viewport from list of 4+ common resolutions
  - Human-like delays: `random.uniform(1.0, 3.0)` between actions
  - Locale: "en-US"
- [ ] Write tests:
  - Navigate to local HTML fixture file (requires Playwright integration test)
  - Extract text and attributes from known selectors
  - Fill and submit a local form
  - Screenshot produces a file
- [x] Handle Playwright not installed gracefully (clear error message)

### 0.5 Email connector

- [x] Create `connectors/email.py` — EmailConnector class
  - `send(to, subject, body, from_addr) -> dict`
  - `check_inbox(from_filter, subject_filter, since_minutes, wait_minutes, poll_interval_seconds) -> list[EmailMessage]`
  - `_search_inbox(from_filter, subject_filter) -> list[EmailMessage]`
  - `_extract_links(text) -> list[str]`
- [x] Create EmailConfig dataclass matching executor config schema
- [x] Add email config section to `config.py`
- [ ] Write tests using MailHog:
  - Send email → appears in MailHog (requires MailHog integration test)
  - Send email → check_inbox finds it with correct from/subject
  - Extract links from email body
  - Timeout when no matching email found

### 0.6 Docker Compose

- [x] Create `docker-compose.yml`:
  - `erasure-executor` service (build from Dockerfile, port 8080)
  - `postgres` service (postgres:16-alpine, port 5432)
  - `mailhog` service (ports 8025/1025)
  - `prometheus` service (port 9090)
  - Volumes: pg_data, artifacts
  - Environment variables for all secrets
- [x] Create `Makefile`:
  - `build` — docker compose build
  - `up` — docker compose up -d
  - `down` — docker compose down
  - `migrate` — run alembic upgrade head in executor container
  - `test` — run pytest in executor container
  - `logs` — docker compose logs -f erasure-executor
- [ ] Verify `make build && make up && make migrate` works cleanly
- [ ] Verify healthz endpoint responds

### 0.7 Config and workspace template

- [x] Create `config/executor.config.yaml` (all sections from design.md section 9.1)
- [ ] Create `config/openclaw.openclaw.json5` (from design.md section 9.2) — deferred
- [x] Create workspace template files:
  - `workspace-template/IDENTITY.md` — agent identity
  - `workspace-template/SOUL.md` — operating principles
  - `workspace-template/AGENTS.md` — execution protocol and hard constraints
  - `workspace-template/TOOLS.md` — tool conventions
- [ ] Create `schemas/executor-config.schema.json` — deferred to Phase 1
- [ ] Create `schemas/erasure-plan.schema.json` — deferred to Phase 1
- [ ] Create `schemas/pii-profile.schema.json` — deferred to Phase 1

---

## Phase 1: First Broker (Week 3-4)

### 1.1 Broker catalog

- [x] Create `broker-catalog/catalog.yaml` with 11 broker entries (id, name, category, removal_method, difficulty, plan_file, recheck_days, notes)
- [x] Implement catalog loader (`catalog.py`): BrokerCatalog class, YAML → validated BrokerEntry dataclasses
- [x] Write catalog validation tests (8 tests: load, ids, missing, invalid category/difficulty, duplicates, real catalog)

### 1.2 match.identity task type

- [x] Create `matching/identity.py`:
  - `normalize_name(name) -> str` — lowercase, strip suffixes (Jr/Sr/III), handle initials
  - `names_match(a, b) -> tuple[bool, float]` — exact, fuzzy (rapidfuzz token_sort_ratio), first+last, initial match
  - `location_matches(listing_loc, profile_addresses) -> tuple[bool, float]` — city+state with full state name normalization
  - `age_matches(listing_age, dob, tolerance) -> tuple[bool, float]` — calculated age within tolerance
  - `phone_matches(listing_phone, profile_phones) -> tuple[bool, float]` — normalized 10-digit comparison
  - `relatives_match(listing_relatives, profile_relatives) -> tuple[bool, float]` — fuzzy name overlap
  - `heuristic_match(listing, profile) -> MatchResult` — weighted scoring (name=0.35, location=0.25, age=0.15, phone=0.10, relatives=0.15)
  - `_llm_verify_match()` — borderline verification via llm.json task
- [x] Register `match.identity` in `tasks/registry.py`:
  - Resolves profile data from refs/state
  - Builds listings from scrape.rendered extracted output
  - Runs heuristic_match for each
  - Runs llm_verify for borderline cases (0.4-0.8 confidence)
  - Returns matched listings above threshold
- [x] Write tests (32 tests covering name normalization, matching, location, age, phone, relatives, heuristic)

### 1.3 scrape.rendered task type

- [x] Register `scrape.rendered` in `tasks/registry.py` (done in Phase 0):
  - Resolve url_template with params
  - Call BrowserConnector.navigate(url, wait_for)
  - Call BrowserConnector.extract(page, selectors) if extract defined
  - Execute actions list if defined (fill, click sequences)
  - Save screenshot as artifact if screenshot=true
  - Return extracted data
- [ ] Handle Playwright errors (deferred to Phase 3 hardening):
  - Timeout → TaskExecutionError(transient=True)
  - Selector not found → TaskExecutionError(transient=False)
  - Navigation failure → TaskExecutionError(transient=True)
- [ ] Write integration tests with local HTML fixture (requires Playwright)

### 1.4 form.submit task type

- [x] FormConnector class already in `connectors/form.py` (created in Phase 0)
- [x] Register `form.submit` in `tasks/registry.py`:
  - Navigate to URL via BrowserConnector
  - Detect form using hints or heuristics via FormConnector
  - Resolve field values from state/params (including `{{ref}}` syntax)
  - Fill and submit via FormConnector.fill_and_submit()
  - Screenshot before and after submit
  - Return submit result with form action, method, fields, success/error
- [ ] Write integration tests with local HTML form fixture (requires Playwright)

### 1.5 Email task types

- [x] Register `email.send` in `tasks/registry.py` (done in Phase 0)
- [x] Register `email.check` in `tasks/registry.py` (done in Phase 0)
- [x] Register `email.click_verify` in `tasks/registry.py` (done in Phase 0)
- [ ] Write integration tests using MailHog (requires Docker)

### 1.6 broker.update_status task type

- [x] Register `broker.update_status` in `tasks/registry.py`:
  - Resolve broker_id, status, listing data from input/refs
  - Structure listing update with timestamp fields based on status transition
  - Record removal_action if status is removal_submitted/removal_failed
  - Set recheck_after based on recheck_days
  - Update Prometheus metrics (REMOVALS_TOTAL, LISTINGS_TOTAL)
  - Return structured result for runner to persist
- [ ] Write DB integration tests (requires PostgreSQL):
  - New listing → inserted with status=found
  - Status update → found → removal_submitted → pending_verification
  - recheck_after set correctly

### 1.7 wait.delay task type

- [x] Register `wait.delay` in `tasks/registry.py`:
  - Short delays (< 5 min): inline sleep
  - Long delays: return resume_at for deferred execution
  - Supports hours/minutes/seconds input

### 1.8 Spokeo plan

- [x] Research Spokeo opt-out flow:
  - Search URL: `/FirstName-LastName/City/State`
  - Opt-out URL: `/optout` with profile URL + email fields
  - Email verification required (click link in email from spokeo.com)
  - Processing: 24-72h after verification
- [x] Write `workspace-template/plans/brokers/spokeo.yaml`:
  - 8 tasks: search_listing → match_results → record_found → submit_optout (approval gate) → record_submitted → check_verification_email → click_verify_link → update_final_status
  - Correct dependency chain
  - params_schema with required: full_name, city, state, profile_id, agent_email
- [x] Write plan validation tests (6 tests: loads, tasks, approval gate, dependencies, params, task types)
- [ ] End-to-end test against real Spokeo (deferred — requires live browser + email)

---

## Phase 2: Broker Expansion (Week 5-8)

### 2.1 Broker plans

For each broker, the work is:
1. Research opt-out flow (selectors, forms, verification)
2. Write YAML plan
3. Test discovery against live site
4. Test removal flow
5. Document anti-bot behavior

- [x] BeenVerified plan (`brokers/beenverified.yaml`) — search → match → record → approve submit → email verify → update
- [x] Intelius plan (`brokers/intelius.yaml`) — submit optout form → email verify (15 min expiry) → update
- [x] FamilyTreeNow plan (`brokers/familytreenow.yaml`) — search → match → record → submit → email verify → update
- [x] TruePeopleSearch plan (`brokers/truepeoplesearch.yaml`) — search → match → record → submit → email verify → update
- [x] FastPeopleSearch plan (`brokers/fastpeoplesearch.yaml`) — search → match → record → submit → email verify → update
- [x] PeopleFinder plan (`brokers/peoplefinder.yaml`) — search → match → record → submit → email verify → update
- [x] WhitePages plan (`brokers/whitepages.yaml`) — phone verify step → human queue via queue.human_action
- [x] Radaris plan (`brokers/radaris.yaml`) — submit privacy control → email verify → update (account may be required)
- [x] Acxiom plan (`brokers/acxiom.yaml`) — marketing data broker, submit optout → email verify → update (~2 week processing)
- [x] Parametrized test suite validates all 10 plans: loads, has tasks, params, unique IDs, valid deps, approval gates, human queue, update status

### 2.2 Human action queue

- [x] Add `queue.human_action` task type to plan schema (TaskType Literal, now 12 types)
- [x] Add `_execute_queue_human_action` to `tasks/registry.py`:
  - Insert into human_action_queue table
  - Include: action_needed, instructions, priority, broker_id
  - Mark task as succeeded (run continues, human action is async)
  - Increment HUMAN_QUEUE_PENDING Prometheus metric
- [x] WhitePages plan exercises queue.human_action for phone verification
- [ ] Add API endpoints (deferred to Phase 2.4):
  - `GET /v1/queue` — list pending items, ordered by priority desc
  - `GET /v1/queue/{queue_id}` — single item detail
  - `POST /v1/queue/{queue_id}/complete` — mark done with optional notes

### 2.3 Scheduler

- [x] Implement `engine/scheduler.py` — ErasureScheduler class:
  - `get_due_jobs() -> list[ScanJob]` — queries scan_schedule for enabled jobs where next_run_at <= now
  - `mark_started(schedule_id, run_id)` — records run_id, advances next_run_at by interval_days
  - `initialize_for_profile(profile_id, catalog_brokers)` — creates scan schedules for all catalog brokers (skips brokers without plan_file)
- [x] Background daemon thread with poll loop:
  - Polls every `poll_interval_seconds` (default 300s)
  - For each due job: create Run via create_run_fn callback, mark_started
  - Rate limit: max 1 concurrent run per broker per poll cycle
- [x] Wire into profile creation: `POST /v1/profiles` calls `scheduler.initialize_for_profile`
- [x] Wire scheduler start/stop into FastAPI startup/shutdown hooks
- [x] Write tests (4 tests):
  - Scheduler creation with custom poll interval
  - Start/stop daemon thread lifecycle
  - initialize_for_profile creates schedules, skips brokers without plan_file
  - ScanJob dataclass

### 2.4 Status API

- [x] `GET /v1/brokers` — wired to use BrokerCatalog for name/category/difficulty
- [x] `GET /v1/brokers/{broker_id}/listings` — returns broker_listings rows for broker
- [x] `GET /v1/schedule` — returns scan_schedule rows with next_run_at
- [x] `POST /v1/schedule/{schedule_id}/trigger` — set next_run_at to now()
- [x] `GET /v1/queue`, `POST /v1/queue/{queue_id}/complete` — human queue endpoints
- [ ] Write API integration tests for all endpoints (requires DB)

---

## Phase 3: Hardening (Week 9-10)

### 3.1 Anti-bot stealth

- [x] Inline stealth patches in BrowserConnector (navigator.webdriver override, plugins, languages, chrome.runtime)
- [x] Configurable request delays: `browser.min_delay_ms`, `browser.max_delay_ms` (default 1000-3000ms)
- [x] Proxy support: `browser.proxy_url`, `proxy_username`, `proxy_password` wired into Playwright launch
- [x] BrokerRateLimiter: token bucket rate limiter keyed by broker domain (`browser.rate_limit_per_broker_per_hour`, default 30)
- [x] robots.txt checker: `RobotsTxtChecker` with per-domain caching, fails open (`browser.check_robots_txt`, default true)
- [x] All new BrowserConfig fields wired through config.py → registry.py → BrowserConnector
- [x] Tests: rate limiter (5 tests), browser config (3 tests), robots.txt fail-open (1 test)

### 3.2 CAPTCHA handling

- [x] Add `captcha.solve` task type to plan schema (TaskType Literal, now 13 types)
- [x] Add `_execute_captcha_solve` to registry.py:
  - Screenshots CAPTCHA element via ref
  - Inserts into human_action_queue with instructions and screenshot path
  - Returns immediately (async human action)
  - Increments HUMAN_QUEUE_PENDING metric
- [ ] Simple web page for CAPTCHA solving (deferred — requires frontend)
- [ ] Third-party solver integration stub (deferred)

### 3.3 PII security

- [x] RedactingFilter already wired into root logger via `configure_logging(redact=True)` — done in Phase 0
- [x] `set_redaction_terms()` available for loading PII terms at runtime — done in Phase 0
- [x] SSRF validation in `connectors/http.py` — done in Phase 0:
  - Blocks private CIDRs: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8, 169.254.0.0/16, ::1/128, fc00::/7, fe80::/10
  - Validates URL before every request + on redirects
- [x] `auth.py` already uses `hmac.compare_digest()` — done in Phase 0
- [ ] Integration test: run a full broker plan, grep all log output for PII terms → 0 matches

### 3.4 Artifact lifecycle

- [x] Create `engine/artifact_cleanup.py` — ArtifactCleanup background job:
  - Deletes run_artifacts where kind='html' and age > `pii.artifact_retention_html_days`
  - Deletes run_artifacts where kind='screenshot' and age > `pii.artifact_retention_screenshot_days`
  - Keeps kind='confirmation' and kind='receipt' indefinitely (retention_days=-1)
  - Removes corresponding files from disk
  - Runs as daemon thread with configurable poll interval
- [x] Retention already configurable in PIIConfig (html_days, screenshot_days, confirmation_days)
- [x] Tests (5 tests): deletes old html, keeps recent html, deletes old screenshots, keeps confirmations, start/stop

### 3.5 Error resilience

- [x] `_handle_browser_error()` in registry.py — converts Playwright exceptions to TaskExecutionError:
  - TimeoutError → transient=True (retryable)
  - Selector not found → transient=False (site layout changed)
  - Navigation failure (net::ERR_*) → transient=True
  - RobotsTxtBlocked → transient=False
  - Unknown → transient=True (default)
- [x] Wired into scrape.rendered and form.submit executors
- [x] Plan health check endpoint: `POST /v1/plans/{plan_id}/check`
  - Validates plan loads and parses
  - Checks all task dependency references are valid
  - Returns health status: healthy | degraded | broken
- [x] Dead letter tracker: `engine/dead_letter.py` — DeadLetterTracker class:
  - Tracks consecutive failures per broker
  - After N consecutive failures (default 3), disables all scan schedules for that broker
  - `record_success()` resets count, `record_failure()` increments and checks threshold
  - `get_dead_lettered()` returns list of disabled broker IDs
- [x] Tests: browser error handling (7 tests), dead letter tracking (7 tests)

---

## Phase 4: CLI & Observability (Week 11-12)

### 4.1 CLI tool

- [ ] Create `packages/erasure-cli/` with Click-based CLI
- [ ] Commands:
  - `id-erase profile create` — interactive prompts for PII fields → POST /v1/profiles
  - `id-erase profile show` — GET /v1/profiles/{id} → display metadata table
  - `id-erase profile delete` — confirm + DELETE /v1/profiles/{id}
  - `id-erase scan` — trigger all brokers → POST /v1/schedule/{id}/trigger for each
  - `id-erase scan <broker>` — trigger single broker
  - `id-erase status` — GET /v1/brokers → formatted table
  - `id-erase status <broker>` — GET /v1/brokers/{id}/listings → formatted table
  - `id-erase queue` — GET /v1/queue → formatted list
  - `id-erase queue complete <id>` — POST /v1/queue/{id}/complete
  - `id-erase schedule` — GET /v1/schedule → formatted table
- [ ] Config: `~/.id-erase/config.yaml` with executor_url and auth_token
- [ ] Write tests for CLI commands (mock API responses)

### 4.2 Prometheus metrics

- [x] Add to `metrics.py`:
  - `erasure_listings_total` (Gauge, labels: broker, status)
  - `erasure_removals_total` (Counter, labels: broker, result)
  - `erasure_scans_total` (Counter, labels: broker, result)
  - `erasure_human_queue_pending` (Gauge)
  - `erasure_match_confidence` (Histogram, labels: broker)
- [x] Wire metrics into broker.update_status (REMOVALS_TOTAL, LISTINGS_TOTAL) — done in Phase 1
- [x] Wire metrics into queue.human_action (HUMAN_QUEUE_PENDING) — done in Phase 2
- [ ] Wire metrics into:
  - Task completion (registry.py)
  - Scheduler run start/complete
  - match.identity confidence scores
- [ ] Write tests: verify metric values after operations

### 4.3 Grafana dashboard

- [ ] Create `config/grafana/dashboards/id-erase.json`:
  - Row: Broker coverage (table: broker × status counts)
  - Row: Removal success rate (bar chart over time)
  - Row: Scan frequency (graph: scans/day per broker)
  - Row: Human queue depth (gauge)
  - Row: Match confidence distribution (histogram)
- [ ] Provision via Docker Compose grafana service

### 4.4 Alerting

- [ ] Create `config/prometheus/alerts.yml`:
  - `ErasurePlanFailureRate` — rate of plan failures > 50% for 1h per broker
  - `ErasureHumanQueueBacklog` — pending queue items > 10
  - `ErasureSchedulerStalled` — no scans completed in 48h
  - `ErasurePIIExposure` — PII pattern detected in logs (if log monitoring available)

---

## Phase 5: Legal & Discovery (Future)

- [ ] CCPA deletion request template
- [ ] GDPR Article 17 request template
- [ ] `legal.generate_request` task type (LLM-powered, template-based)
- [ ] `discover.search_engine` task type (Google/Bing search for user's name)
- [ ] LLM classifier: is this search result a data broker listing?
- [ ] Auto-add discovered brokers to catalog (pending plan creation)
- [ ] Google content removal request integration

---

## Phase 6: Multi-User & Web UI (Future)

- [ ] Row-level security on all tables (profile_id column)
- [ ] JWT auth with user claims (replace bearer token)
- [ ] Per-user encryption keys
- [ ] Web dashboard (Supabase + Vercel or equivalent)
  - Profile management
  - Broker status visualization
  - Human action queue
  - Scan history
- [ ] Hosted deployment manifests (Kubernetes)
- [ ] Onboarding flow for non-technical users
