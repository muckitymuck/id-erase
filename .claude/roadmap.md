# id-erase: Roadmap

| Field | Value |
|-------|-------|
| Version | 0.1.0 |
| Date | 2026-02-22 |
| Status | Draft |

---

## Timeline Summary

| Phase | Name | Duration | Cumulative | Description |
|-------|------|----------|------------|-------------|
| 0 | Foundation | Week 1-2 | 2 weeks | Fork executor, PII vault, browser/email connectors, Docker Compose |
| 1 | First Broker | Week 3-4 | 4 weeks | Spokeo end-to-end: discovery, matching, removal, verification |
| 2 | Broker Expansion | Week 5-8 | 8 weeks | 5-10 broker plans, human action queue, scheduler |
| 3 | Hardening | Week 9-10 | 10 weeks | Anti-bot stealth, CAPTCHA, PII security, artifact expiration |
| 4 | CLI & Observability | Week 11-12 | 12 weeks | CLI dashboard, status reports, broken plan detection |
| 5 | Legal & Discovery | Future | — | CCPA/GDPR templates, broker discovery, Google removal |
| 6 | Multi-User & Web UI | Future | — | Multi-tenant, hosted option, web dashboard |

**MVP (self-hosted, single-user, 5-10 brokers): ~8 weeks**
**Production-ready (hardened, monitored): ~12 weeks**

---

## Phase 0: Foundation (Week 1-2)

### Goals
- Functional executor service adapted from seo-fetch
- PII profile encrypted storage
- Playwright browser connector working
- Email connector working
- Local dev environment with Docker Compose

### Deliverables

#### 0.1 Fork seo-executor into erasure-executor
- Copy `packages/seo-executor/` to `packages/erasure-executor/`
- Rename modules: `seo_executor` → `erasure_executor`
- Update `pyproject.toml` with new name and dependencies (add `playwright`, `cryptography`)
- Verify existing tests pass with new module paths
- Remove SEO-specific code (seo-specific scraper fields, SEO plan references)

#### 0.2 Database schema — new tables
- Add Alembic migration for `pii_profiles` table
- Add Alembic migration for `broker_listings` table
- Add Alembic migration for `removal_actions` table
- Add Alembic migration for `human_action_queue` table
- Add Alembic migration for `scan_schedule` table
- Add SQLAlchemy ORM models for all new tables
- Add indexes per design.md spec

#### 0.3 PII vault
- Implement `engine/pii_vault.py` with AES-256-GCM encrypt/decrypt
- Add PII profile Pydantic schema (`schemas/pii.py`)
- Add API endpoints: POST/GET/DELETE `/v1/profiles`
- Write tests: encrypt → decrypt round-trip, key validation, data_hash

#### 0.4 Browser connector (Playwright)
- Implement `connectors/browser.py` with BrowserConnector class
- Stealth basics: randomized UA, viewport, human-like delays
- Methods: navigate, extract, fill_form, click_and_wait, screenshot
- Add `playwright` to pyproject.toml dependencies
- Write tests with a local HTML fixture

#### 0.5 Email connector
- Implement `connectors/email.py` with EmailConnector class
- Methods: send, check_inbox, extract_links
- Add email config section to executor config schema
- Write tests using MailHog in Docker Compose

#### 0.6 Docker Compose
- Create `docker-compose.yml` with: erasure-executor, postgres, mailhog, prometheus
- Create `Dockerfile` for erasure-executor (non-root, Playwright deps installed)
- Create `Makefile` with targets: `build`, `up`, `down`, `migrate`, `test`
- Verify full stack starts and healthz responds

#### 0.7 Config and workspace template
- Create `config/executor.config.yaml` with all sections from design.md
- Create `config/openclaw.openclaw.json5`
- Create `workspace-template/IDENTITY.md`, `SOUL.md`, `AGENTS.md`, `TOOLS.md`

### Exit Criteria
- [ ] `make up` starts all services successfully
- [ ] PII profile can be created, retrieved (metadata only), and deleted via API
- [ ] Browser connector can navigate a page and extract text
- [ ] Email connector can send via MailHog SMTP and read via IMAP
- [ ] Existing seo-fetch tests pass in new module structure
- [ ] All new code has tests with >70% coverage

---

## Phase 1: First Broker (Week 3-4)

### Goals
- Complete Spokeo plan: discovery → matching → removal → verification
- All new task types implemented and tested
- End-to-end removal flow works against real Spokeo (or realistic mock)

### Deliverables

#### 1.1 Broker catalog
- Create `broker-catalog/catalog.yaml` with initial 10 broker entries
- Implement catalog loader in executor (YAML → dict)
- Write catalog schema validation

#### 1.2 match.identity task type
- Implement `matching/identity.py` with heuristic scoring
- Name normalization (case, initials, suffixes, prefixes)
- Location matching (city+state against address history)
- Age matching (calculated age vs. DOB with tolerance)
- Implement LLM verification path for borderline cases
- Register `match.identity` in task registry
- Write tests with various match scenarios (exact, partial, no match, namesake)

#### 1.3 scrape.rendered task type
- Wire `scrape.rendered` in task registry to BrowserConnector
- Support: url_template, wait_for, extract (selectors), screenshot, actions
- Handle Playwright timeouts gracefully
- Write tests

#### 1.4 form.submit task type
- Implement `connectors/form.py` with FormConnector
- Register `form.submit` in task registry
- Support: form_hints, values (with template resolution), screenshot
- Write tests with local HTML form fixture

#### 1.5 Email task types
- Register `email.send` in task registry → EmailConnector.send()
- Register `email.check` in task registry → EmailConnector.check_inbox()
- Register `email.click_verify` → BrowserConnector.navigate(link)
- Write tests using MailHog

#### 1.6 broker.update_status task type
- Implement status update logic (insert/update broker_listings, insert removal_actions)
- Register in task registry
- Write tests

#### 1.7 wait.delay task type
- Implement pause mechanism (for post-removal verification waits)
- For MVP: store resume time in DB, runner skips task until time passes
- Register in task registry

#### 1.8 Spokeo plan
- Write `workspace-template/plans/brokers/spokeo.yaml`
- Research actual Spokeo opt-out flow (selectors, form fields, email verification)
- Test discovery against real Spokeo
- Test opt-out submission (with human approval)
- Test email verification flow
- Document any anti-bot issues encountered

### Exit Criteria
- [ ] All 6 new task types registered and tested
- [ ] Spokeo plan executes end-to-end (discovery → match → opt-out → email verify → status update)
- [ ] Approval gate blocks before opt-out submission
- [ ] match.identity correctly filters false positives
- [ ] Artifacts stored: search screenshots, opt-out confirmation, verification screenshot
- [ ] broker_listings table tracks status correctly

---

## Phase 2: Broker Expansion (Week 5-8)

### Goals
- 5-10 working broker plans
- Human action queue for non-automatable brokers
- Scheduler for recurring scans
- Basic status view (CLI or API)

### Deliverables

#### 2.1 Additional broker plans
Write and test YAML plans for (priority order):
1. BeenVerified (web form, easy)
2. Intelius (web form, easy)
3. FamilyTreeNow (web form, easy)
4. TruePeopleSearch (web form, easy)
5. FastPeopleSearch (web form, easy)
6. PeopleFinder (web form, easy)
7. WhitePages (phone verify — human queue for verification step)
8. Radaris (account required — more complex plan)
9. Acxiom (web form + account, medium)

Each broker plan requires:
- Research actual opt-out flow (document selectors, form fields, verification method)
- Write YAML plan with correct task DAG
- Test discovery against live site
- Test removal flow (may need real data or mock)
- Document anti-bot behavior encountered

#### 2.2 Human action queue
- Implement human_action_queue API endpoints (GET `/v1/queue`, POST `/v1/queue/{id}/complete`)
- Add `queue.human_action` task type that inserts into queue and marks run as succeeded
- Use for: phone verification, fax/mail, CAPTCHA (initially)
- Write tests

#### 2.3 Scheduler
- Implement `engine/scheduler.py` per design.md
- Background thread in executor that polls scan_schedule every 5 minutes
- Auto-creates scan schedules when profile is created (initialize_for_profile)
- Triggers discovery/verification runs for due brokers
- Write tests

#### 2.4 Status API
- GET `/v1/brokers` — all brokers with aggregated status (found/removed/pending counts)
- GET `/v1/brokers/{broker_id}/listings` — detailed listing status for one broker
- GET `/v1/schedule` — upcoming scheduled scans
- POST `/v1/schedule/{id}/trigger` — manual trigger
- Write tests

#### 2.5 CLI status tool (optional)
- Simple Python script or Click CLI that calls status APIs and prints table
- Show: broker name | listings found | removed | pending | next scan
- Show: human action queue items pending

### Exit Criteria
- [ ] 5+ broker plans working end-to-end
- [ ] Human action queue items created for non-automatable steps
- [ ] Scheduler triggers recurring scans on schedule
- [ ] Status API returns accurate broker/listing data
- [ ] No duplicate removal submissions (idempotency working)

---

## Phase 3: Hardening (Week 9-10)

### Goals
- Robust anti-bot measures
- CAPTCHA handling strategy
- PII security hardened
- Artifact lifecycle management

### Deliverables

#### 3.1 Anti-bot stealth
- Integrate `playwright-stealth` or equivalent
- Randomized request timing (configurable min/max delays)
- Proxy support in BrowserConnector (SOCKS5/HTTP)
- Rate limiting: configurable max requests per broker per hour
- Respect robots.txt (configurable — on by default)
- Fingerprint randomization (WebGL, canvas, timezone)

#### 3.2 CAPTCHA handling
- Add `captcha.manual_queue` task type — screenshots CAPTCHA, queues for human solve
- Human solves CAPTCHA through a simple web page or API
- Agent retries after human provides solution
- Integration point for future third-party solver (2Captcha API stub)

#### 3.3 PII security hardening
- Log redaction filter active on all loggers (`utils/redact.py`)
- Load PII terms from profile into redaction filter at runtime
- Verify no PII appears in any log output (test with grep)
- Verify no PII in artifacts except encrypted profile
- SSRF validation on all outbound URLs (block private CIDRs)
- Bearer token comparison uses `hmac.compare_digest()`

#### 3.4 Artifact lifecycle
- Background job: delete HTML artifacts older than 7 days
- Background job: delete screenshot artifacts older than 30 days
- Keep confirmation/receipt artifacts indefinitely
- Configurable retention periods in executor config

#### 3.5 Error handling & resilience
- Graceful handling of broker site changes (selector not found → clear error, not crash)
- Plan health check: detect when a plan's selectors no longer match the broker site
- Exponential backoff for transient failures (network, 5xx, rate limits)
- Dead letter queue for plans that fail repeatedly

### Exit Criteria
- [ ] No PII appears in any log output (verified by test)
- [ ] Browser connector uses stealth measures
- [ ] CAPTCHA encountered → human queue item created
- [ ] Artifacts auto-expire per retention policy
- [ ] Bearer token auth uses timing-safe comparison
- [ ] SSRF validation blocks private IPs
- [ ] Plan health check detects broken selectors

---

## Phase 4: CLI & Observability (Week 11-12)

### Goals
- User-friendly CLI for managing the agent
- Operational dashboards
- Alerting for important events

### Deliverables

#### 4.1 CLI tool
- `id-erase profile create` — interactive PII profile setup
- `id-erase profile show` — display profile metadata (no raw PII)
- `id-erase profile delete` — delete profile + all data
- `id-erase scan` — trigger full discovery sweep
- `id-erase scan <broker>` — trigger single broker scan
- `id-erase status` — table of all brokers with listing counts
- `id-erase status <broker>` — detailed listings for one broker
- `id-erase queue` — show pending human actions
- `id-erase queue complete <id>` — mark action done
- `id-erase schedule` — show upcoming scans

#### 4.2 Prometheus metrics
- `erasure_listings_total{broker, status}` — gauge of listing counts
- `erasure_removals_total{broker, result}` — counter of removal attempts
- `erasure_scans_total{broker, result}` — counter of scan runs
- `erasure_human_queue_pending` — gauge of pending human actions
- `erasure_match_confidence{broker}` — histogram of match confidence scores

#### 4.3 Grafana dashboard
- Pre-built dashboard JSON for id-erase metrics
- Panels: broker coverage, removal success rate, scan frequency, queue depth
- Provisioned via Docker Compose

#### 4.4 Alerting
- Prometheus alert rules:
  - Plan failure rate > 50% for any broker → broken plan likely
  - Human queue depth > 10 → user attention needed
  - No scans completed in 48h → scheduler may be stuck
  - PII exposure detected in logs → critical

### Exit Criteria
- [ ] CLI covers all core workflows
- [ ] Prometheus metrics exported for all key operations
- [ ] Grafana dashboard shows broker status at a glance
- [ ] Alert rules configured for critical conditions

---

## Phase 5: Legal & Discovery (Future)

### Goals
- Formal legal request generation (CCPA/GDPR)
- Automated broker discovery
- Google search result removal

### Deliverables

#### 5.1 Legal letter generation
- CCPA deletion request template (California residents)
- GDPR Article 17 request template (EU residents)
- `legal.generate_request` task type — LLM generates personalized letter from template
- Queue generated letters for human review + postal mail/email send

#### 5.2 Broker discovery
- Search engines (Google, Bing) for user's name + PII to find unknown broker listings
- `discover.search_engine` task type
- LLM classifies results: is this a data broker listing?
- New brokers added to catalog automatically (pending plan creation)

#### 5.3 Google search removal
- Submit removal requests via Google's content removal tool
- Track removal status
- Re-check Google results after removal

---

## Phase 6: Multi-User & Web UI (Future)

### Goals
- Support multiple users with isolated data
- Web dashboard for non-technical users
- Hosted deployment option

### Deliverables

#### 6.1 Multi-tenant data model
- Row-level security on all tables (profile_id isolation)
- JWT auth with user claims
- Separate encryption keys per user

#### 6.2 Web dashboard
- Profile management UI
- Broker status visualization
- Human action queue UI
- Scan history and logs
- Built with: Supabase + Vercel (or similar)

#### 6.3 Hosted deployment
- Kubernetes manifests for production
- Managed PostgreSQL
- Managed email (or shared agent email with per-user routing)
- Billing integration

---

## Dependency Graph

```
Phase 0 (Foundation)
    │
    ├──► Phase 1 (First Broker)
    │        │
    │        ├──► Phase 2 (Broker Expansion)
    │        │        │
    │        │        ├──► Phase 3 (Hardening)
    │        │        │        │
    │        │        │        └──► Phase 4 (CLI & Observability)
    │        │        │
    │        │        └──► Phase 5 (Legal & Discovery)
    │        │
    │        └──► Phase 3 can start in parallel with Phase 2
    │
    Phase 6 (Multi-User) depends on Phase 4
```

**Critical path to MVP:** Phase 0 → Phase 1 → Phase 2 (8 weeks)
**Critical path to production:** + Phase 3 → Phase 4 (12 weeks)
