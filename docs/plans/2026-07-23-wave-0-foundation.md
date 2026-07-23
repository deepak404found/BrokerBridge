# Wave 0 — Foundation / Local Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a runnable Local Lab: Docker Compose (api, worker stub, postgres, redis, redpanda), FastAPI with `/docs` + `/health`, and `/admin` shell from the sample HTML UX.

**Architecture:** Single FastAPI app mounts static admin and exposes OpenAPI. Compose wires real Postgres/Redis/Redpanda; app uses settings from env. No domain features yet beyond health.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Docker Compose, structlog (basic), pydantic-settings.

## Global Constraints

- Specs: `local/PRD.md` §15–16, `local/TDD.md` §24, §32.
- Stack services only: api, worker, postgres, redis, redpanda.
- Default mocks later; W0 may not yet have providers — health + static admin is enough.
- Follow `CLAUDE.md` / `.cursor/rules`.
- When DoD met: **ask user before commit**, then changelog.

---

### Task 1: Python project skeleton

**Files:**
- Create: `pyproject.toml` or `requirements.txt`
- Create: `app/__init__.py`
- Create: `app/main.py`
- Create: `app/config/settings.py`
- Create: `.env.example`
- Create: `.gitignore`

- [ ] **Step 1:** Add dependencies: `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `httpx` (dev), `pytest`, `pytest-asyncio`
- [ ] **Step 2:** Implement `Settings` with `APP_ENV`, `DATABASE_URL`, `REDIS_URL`, `REDPANDA_BROKERS`, `DOCS_ENABLED`, `ADMIN_UI_ENABLED`, `LOG_LEVEL`
- [ ] **Step 3:** Create minimal FastAPI app with title `BrokerBridge API`, `docs_url="/docs"`, `redoc_url="/redoc"`
- [ ] **Step 4:** Commit only after user approval at end of wave (do not commit mid-wave unless user asks)

---

### Task 2: Health routes

**Files:**
- Create: `app/api/router.py`
- Create: `app/api/routes/health.py`
- Create: `tests/test_health.py`

- [ ] **Step 1:** Write failing test for `GET /health/live` → `{"status":"ok"}`
- [ ] **Step 2:** Implement `/health/live` and `/health/ready` (ready may return degraded if DB not wired yet — document; W1 hardens readiness)
- [ ] **Step 3:** Run `pytest tests/test_health.py -v` — expect PASS

---

### Task 3: Docker Compose Local Lab

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `README.md` (clone → compose → URLs)

- [ ] **Step 1:** Compose services: `api`, `worker` (same image, sleep/stub command OK), `postgres`, `redis`, `redpanda`
- [ ] **Step 2:** API exposes `8000`; healthcheck on `/health/live`
- [ ] **Step 3:** Document URLs: `/admin`, `/docs`, `/redoc`, `/api/v1` (api prefix may be empty until W1)
- [ ] **Step 4:** Verify `docker compose up --build` starts (may need user machine Docker)

---

### Task 4: Admin shell from sample HTML

**Files:**
- Create: `app/static/admin/` (copy/adapt from `local/brokerbridge_operations_platform.html`)
- Modify: `app/main.py` — mount StaticFiles at `/admin`
- Create: `app/static/admin/js/api.js` stub (baseURL + placeholder auth)

- [ ] **Step 1:** Copy sample HTML into `app/static/admin/index.html` (keep UX)
- [ ] **Step 2:** Add nav link / button to `/docs`
- [ ] **Step 3:** Mount static files; optional `GET /` → redirect `/admin`
- [ ] **Step 4:** Smoke: open `/admin` in browser or curl HTML 200

---

### Task 5: Worker stub + logging

**Files:**
- Create: `app/workers/main.py` (log heartbeat loop or idle)
- Modify: `docker-compose.yml` worker command

- [ ] **Step 1:** Worker process starts and logs JSON-ish heartbeat every N seconds
- [ ] **Step 2:** Compose worker service uses same image

---

### Task 6: Wave 0 verification + handoff

- [ ] **Step 1:** Run pytest
- [ ] **Step 2:** Confirm `/docs` OpenAPI loads
- [ ] **Step 3:** Confirm `/admin` serves
- [ ] **Step 4:** Update master plan checkbox for W0 when user accepts
- [ ] **Step 5:** **Ask user:** “Wave 0 tested. Commit and update changelog?”
- [ ] **Step 6:** On yes — commit + `CHANGELOG.md` + `docs/changelogs/WAVE-00.md` per rules

## Definition of Done

- [ ] `docker compose up --build` brings up stack
- [ ] `/health/live` works
- [ ] `/docs` and `/redoc` work
- [ ] `/admin` shows operations shell (may still use mock UI data)
- [ ] README lists Local Lab URLs
- [ ] User offered commit + changelog

## Out of Scope (W0)

- Auth, DB models, providers, orders, IP orchestration
- Wiring Admin pages to real APIs (starts W1+)
