# id-erase: Product Requirements Document

| Field | Value |
|-------|-------|
| Version | 0.1.0 |
| Date | 2026-02-22 |
| Owner | Andy |
| Status | Draft |

---

## 1. Vision

id-erase is an open-source, self-hosted agent that automatically discovers and removes personal information from data brokers and people-search sites. Built on the OpenClaw agent framework, it brings the same deterministic, plan-driven execution model proven in the SEO BuildPlan Engine to the domain of personal privacy.

The goal: give individuals the same data removal capability that paid services like Aura, DeleteMe, and Incogni provide — but self-hosted, transparent, and fully under their control.

## 2. Problem Statement

Data brokers aggregate and sell personal information — names, addresses, phone numbers, emails, relatives, income estimates — across hundreds of sites. This data powers background checks, targeted advertising, identity fraud, and unwanted surveillance.

Removing yourself is technically possible but practically infeasible:

- **100-200+ broker sites** each have unique opt-out processes
- **Opt-out forms vary wildly** — web forms, email verification, phone verification, fax, postal mail
- **Data reappears** — brokers re-scrape and re-list information within weeks
- **Paid services are opaque** — users pay $10-25/month with no visibility into what's actually happening
- **No single master opt-out** exists

id-erase solves this by encoding each broker's removal workflow as a deterministic YAML plan, executing them through an automated agent with human-in-the-loop approval gates, and continuously monitoring for re-listings.

## 3. Target Users

### Primary: Self-hosting privacy-conscious individual (MVP)
- Comfortable running Docker Compose
- Wants control over their PII and removal process
- Willing to handle manual steps the agent can't automate (phone verification, fax)

### Future: Non-technical users (post-MVP)
- Would use a hosted version with a web dashboard
- Needs a simple onboarding flow (enter your info, let the agent work)

## 4. Core Requirements

### 4.1 P0 — Must Ship (MVP)

#### PII Profile Management

| ID | Requirement | Rationale |
|----|-------------|-----------|
| PII-01 | User can create a PII profile with name, aliases, DOB, addresses, phones, emails, and relatives | Required to search brokers and match results |
| PII-02 | PII profile is encrypted at rest using AES-256-GCM | PII is sensitive data; must be protected even if DB is compromised |
| PII-03 | PII is never written to logs or unencrypted artifacts | Prevents accidental exposure through log aggregation or artifact browsing |
| PII-04 | PII profile can be deleted entirely by the user | User must have full control over their data |

#### Broker Discovery & Matching

| ID | Requirement | Rationale |
|----|-------------|-----------|
| DISC-01 | Agent can search a broker site for listings matching the user's PII | Core discovery functionality |
| DISC-02 | Agent uses LLM + heuristic matching to verify listings belong to the user (not a namesake) | Prevents false positives — submitting opt-outs for the wrong person |
| DISC-03 | Match results include a confidence score (0.0-1.0) | Enables threshold-based approval gating |
| DISC-04 | Listings below confidence threshold are flagged for human review | Prevents automated action on uncertain matches |

#### Removal Execution

| ID | Requirement | Rationale |
|----|-------------|-----------|
| REM-01 | Agent can submit web-based opt-out forms via Playwright browser automation | Most brokers use web forms |
| REM-02 | Agent has its own email address for verification workflows | Many brokers require email verification |
| REM-03 | Agent can send emails and poll inbox for verification links | Completes email verification loops |
| REM-04 | Agent can click email verification links via browser automation | Finalizes email-verified opt-outs |
| REM-05 | First removal attempt per broker requires approval gate | Human oversight before taking action |
| REM-06 | Actions the agent cannot perform are queued for human action | Handles phone verification, fax, postal mail, CAPTCHA |

#### Status Tracking

| ID | Requirement | Rationale |
|----|-------------|-----------|
| STAT-01 | Each broker listing has a tracked lifecycle status (found → removal_submitted → pending_verification → removed → reappeared) | Visibility into removal progress |
| STAT-02 | All removal actions are recorded with timestamps and confirmation IDs | Audit trail |
| STAT-03 | Agent re-checks brokers on a configurable schedule to detect re-listings | Data reappears; must monitor continuously |
| STAT-04 | CLI or API can display current status across all brokers | User needs a single view of their removal progress |

#### Execution Engine (adapted from seo-fetch)

| ID | Requirement | Rationale |
|----|-------------|-----------|
| ENG-01 | Broker workflows are defined as YAML plans with DAG task ordering | Deterministic, auditable, maintainable |
| ENG-02 | Plan execution uses idempotency keys to prevent duplicate submissions | Submitting the same opt-out twice wastes effort and may trigger rate limits |
| ENG-03 | Approval gates block execution until human decision | Human-in-the-loop for side effects |
| ENG-04 | Artifacts (screenshots, HTML, confirmation receipts) are stored for audit | Evidence of actions taken |
| ENG-05 | Executor exposes health check and Prometheus metrics | Operational observability |

#### Security

| ID | Requirement | Rationale |
|----|-------------|-----------|
| SEC-01 | All bearer token comparisons use `hmac.compare_digest()` | Prevents timing attacks |
| SEC-02 | All outbound HTTP requests validate URLs against SSRF blocklist | Prevents internal network scanning |
| SEC-03 | Browser automation uses stealth techniques (randomized UA, viewport, timing) | Avoids bot detection |
| SEC-04 | Egress restricted to known broker domains, email provider, LLM endpoint | Minimizes attack surface |
| SEC-05 | Scraped broker content treated as untrusted (prompt injection risk) | Brokers could inject malicious content |

### 4.2 P1 — After MVP Core

| ID | Requirement | Rationale |
|----|-------------|-----------|
| P1-01 | Scheduler for automated recurring scans (cron-like) | Removes need for manual re-triggering |
| P1-02 | Human action queue with priority ordering | Organizes manual tasks for the user |
| P1-03 | CAPTCHA integration point (manual solve queue or third-party) | Many brokers use CAPTCHAs |
| P1-04 | Broker plan health checks (detect when a plan is broken) | Broker sites change their opt-out flows |
| P1-05 | Artifact auto-expiration (7d for HTML, 30d for screenshots) | Minimizes retained data |
| P1-06 | Support for alternative agent email addresses per broker | Some brokers reject repeated emails |
| P1-07 | Formal CCPA/GDPR deletion request generation | Legal fallback when web opt-outs fail |

### 4.3 P2 — Future (Post-MVP)

| ID | Requirement | Rationale |
|----|-------------|-----------|
| P2-01 | Multi-user / multi-tenant support | Scale beyond single user |
| P2-02 | Web UI dashboard for status visualization | Non-technical user access |
| P2-03 | Google search result removal requests | Removes cached broker listings from search |
| P2-04 | Broker discovery — find new sites listing the user | Growing breadth automatically |
| P2-05 | Credit freeze / monitoring integration | Complementary privacy action |
| P2-06 | Family plan — manage removals for multiple people | Common use case |

## 5. Non-Requirements (MVP)

- Real-time streaming UI
- Mobile app
- Multi-user authentication / RBAC
- Hosted SaaS deployment
- Payment processing
- Legal advice or compliance certification
- Removal guarantees (best-effort only)

## 6. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Broker coverage (plans written) | 5-10 brokers at MVP launch | Count of working YAML plans |
| End-to-end removal success rate | >60% of attempted removals confirmed | broker_listings where status = removed / total removal_submitted |
| False positive rate | <10% of matched listings are wrong person | Manual review of match.identity results |
| Re-listing detection | >90% of re-appearances caught within recheck window | broker_listings where status = reappeared detected within recheck_days |
| PII exposure incidents | 0 | Log audit + artifact review |
| Executor uptime | 99% (self-hosted) | Prometheus availability metric |
| Mean time to removal | <7 days for easy brokers | Avg(verified_at - removal_sent_at) |

## 7. Constraints

- **Self-hosted MVP** — no cloud dependencies beyond email provider and LLM API
- **Single-user** — no multi-tenant isolation needed for MVP
- **OpenClaw fork** — we control the framework; no upstream dependency
- **Same tech stack as seo-fetch** — Python 3.11, FastAPI, SQLAlchemy, PostgreSQL, Playwright
- **No recurring cost for core** — LLM usage is the only variable cost; mock mode available for testing
- **Best-effort removal** — cannot guarantee any broker will comply

## 8. Broker Landscape

### 8.1 Categories

| Category | Examples | Typical Removal Method | Difficulty |
|----------|----------|----------------------|------------|
| People-search | Spokeo, WhitePages, Intelius, BeenVerified, Radaris, PeopleFinder | Web form, email verify | Easy-Medium |
| Public records | FamilyTreeNow, TruePeopleSearch, FastPeopleSearch | Web form | Easy |
| Marketing data | Acxiom, Oracle Data Cloud, Experian Marketing | Web form, account required | Medium |
| Risk/identity | LexisNexis, CoreLogic, TransUnion | Mail/fax, formal request | Hard |
| Social aggregators | Pipl, ZabaSearch, USSearch | Web form, varies | Easy-Medium |

### 8.2 MVP Broker Targets (Phase 1-2)

Priority order based on prevalence and removal difficulty:

1. Spokeo (easy — web form + email verify)
2. BeenVerified (easy — web form)
3. Intelius (easy — web form)
4. WhitePages (medium — phone verify)
5. FamilyTreeNow (easy — web form)
6. TruePeopleSearch (easy — web form)
7. FastPeopleSearch (easy — web form)
8. Radaris (hard — account required)
9. PeopleFinder (easy — web form)
10. Acxiom (medium — web form + account)

### 8.3 Removal Methods Encountered

| Method | Automatable? | Agent Capability |
|--------|-------------|-----------------|
| Web form (simple POST) | Yes | http.request or form.submit |
| Web form (JS-rendered) | Yes | scrape.rendered + form.submit |
| Email verification link | Yes | email.check + email.click_verify |
| Phone verification call | No | Queue for human action |
| Account creation required | Partial | scrape.rendered (create account) + form.submit |
| CAPTCHA | Partial | Manual solve queue or third-party solver |
| Postal mail / fax | No | Generate letter, queue for human |
| Formal legal request (CCPA/GDPR) | Partial | Generate request text, queue for human review + send |

## 9. Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| PostgreSQL 16 | Infrastructure | Database for executor state, broker tracking, PII vault |
| Playwright | Library | Browser automation for JS-heavy broker sites |
| OpenAI-compatible LLM API | Service | Identity matching, form analysis (mock mode available) |
| Email provider (IMAP/SMTP) | Service | Agent's email for verification workflows |
| Docker / Docker Compose | Infrastructure | Local deployment |
| seo-fetch codebase | Reference | Architecture patterns, engine code to fork |

## 10. Open Questions

| # | Question | Impact | Decision Needed By |
|---|----------|--------|--------------------|
| 1 | CAPTCHA handling — manual queue vs. third-party solver? | Affects how many brokers can be fully automated | Phase 1 |
| 2 | Agent email provider — self-hosted vs. commercial? | Some brokers reject disposable domains | Phase 0 |
| 3 | Rate limiting — conservative (1/hour) vs. parallel? | Affects scan speed and bot detection risk | Phase 1 |
| 4 | Broken plan detection — how to alert when broker changes flow? | Affects maintenance burden | Phase 2 |
| 5 | Legal letter generation — include CCPA/GDPR templates? | Enables fallback for resistant brokers | Phase 2 |
| 6 | Broker discovery — search engines for new brokers? | Enables growing breadth automatically | Post-MVP |
