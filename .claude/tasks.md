# id-erase: Task Tracker

| Field | Value |
|-------|-------|
| Version | 0.1.0 |
| Date | 2026-02-22 |
| Status | Phase 1 Complete |

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

- [ ] BeenVerified plan (`brokers/beenverified.yaml`)
- [ ] Intelius plan (`brokers/intelius.yaml`)
- [ ] FamilyTreeNow plan (`brokers/familytreenow.yaml`)
- [ ] TruePeopleSearch plan (`brokers/truepeoplesearch.yaml`)
- [ ] FastPeopleSearch plan (`brokers/fastpeoplesearch.yaml`)
- [ ] PeopleFinder plan (`brokers/peoplefinder.yaml`)
- [ ] WhitePages plan (`brokers/whitepages.yaml`) — phone verify step → human queue
- [ ] Radaris plan (`brokers/radaris.yaml`) — account creation step
- [ ] Acxiom plan (`brokers/acxiom.yaml`)

### 2.2 Human action queue

- [ ] Add `queue.human_action` task type to registry:
  - Insert into human_action_queue table
  - Include: action_needed, instructions, priority, broker_id
  - Mark task as succeeded (run continues, human action is async)
- [ ] Add API endpoints:
  - `GET /v1/queue` — list pending items, ordered by priority desc
  - `GET /v1/queue/{queue_id}` — single item detail
  - `POST /v1/queue/{queue_id}/complete` — mark done with optional notes
- [ ] Write tests

### 2.3 Scheduler

- [ ] Implement `engine/scheduler.py` — ErasureScheduler class:
  - `get_due_jobs() -> list[ScanJob]`
  - `mark_started(schedule_id, run_id)`
  - `initialize_for_profile(profile_id)`
- [ ] Add background thread in `main.py`:
  - Polls every `scheduler.poll_interval_seconds` (default 300s)
  - For each due job: create Run via internal API, mark_started
  - Rate limit: max 1 concurrent run per broker
- [ ] Wire into profile creation: `POST /v1/profiles` calls `initialize_for_profile`
- [ ] Write tests:
  - Due jobs returned correctly based on next_run_at
  - mark_started advances next_run_at by interval_days
  - initialize_for_profile creates schedules for all catalog brokers

### 2.4 Status API

- [ ] `GET /v1/brokers` — returns list of brokers with:
  - broker_id, name, category, difficulty
  - listing_counts: {found, removal_submitted, pending_verification, removed, reappeared, manual_required}
  - last_scan_at, next_scan_at
- [ ] `GET /v1/brokers/{broker_id}/listings` — returns broker_listings rows for broker
- [ ] `GET /v1/schedule` — returns scan_schedule rows with next_run_at
- [ ] `POST /v1/schedule/{schedule_id}/trigger` — set next_run_at to now()
- [ ] Write tests for all endpoints

---

## Phase 3: Hardening (Week 9-10)

### 3.1 Anti-bot stealth

- [ ] Add `playwright-stealth` to dependencies (or equivalent stealth patches)
- [ ] Configurable request delays in executor config: `browser.min_delay_ms`, `browser.max_delay_ms`
- [ ] Proxy support in BrowserConnector: `browser.proxy_url` config option
- [ ] Rate limiter: max N requests per broker per hour (configurable in catalog)
- [ ] robots.txt check before scraping (configurable, on by default)

### 3.2 CAPTCHA handling

- [ ] Add `captcha.manual_queue` task type:
  - Screenshot the CAPTCHA
  - Insert into human_action_queue with screenshot artifact reference
  - Block run until human completes queue item
- [ ] Simple web page for CAPTCHA solving (serves screenshot, accepts text input)
- [ ] Stub for future third-party solver integration (2Captcha API interface)

### 3.3 PII security

- [ ] Wire `utils/redact.py` RedactingFilter into all loggers in `logging.py`
- [ ] At executor startup, load PII terms from profile and add to redaction filter
- [ ] Test: run a full broker plan, grep all log output for any PII term → 0 matches
- [ ] SSRF validation in `connectors/http.py`:
  - Block private CIDRs: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8, 169.254.0.0/16
  - Block localhost, [::1]
  - Validate URL before every request
- [ ] Update `auth.py`: use `hmac.compare_digest()` for bearer token comparison
- [ ] Review all artifact storage: no raw PII in artifact files (only encrypted in pii_profiles)

### 3.4 Artifact lifecycle

- [ ] Background job (runs daily):
  - Delete run_artifacts where kind='html' and age > `pii.artifact_retention.html_days`
  - Delete run_artifacts where kind='screenshot' and age > `pii.artifact_retention.screenshot_days`
  - Delete corresponding files from disk
  - Keep kind='confirmation' and kind='receipt' indefinitely
- [ ] Configurable retention in executor config
- [ ] Write tests

### 3.5 Error resilience

- [ ] Graceful selector-not-found handling: clear error message with broker_id and selector
- [ ] Plan health check endpoint: `POST /v1/plans/{plan_id}/check`
  - Runs discovery step only (no removal)
  - Reports which selectors matched vs. failed
  - Returns health status: healthy | degraded | broken
- [ ] Dead letter tracking: after 3 consecutive plan failures for a broker, disable schedule and alert

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
- [ ] Wire metrics into:
  - Task completion (registry.py)
  - broker.update_status
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
