# Wave 0 — Foundation / Local Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Stand up a runnable Local Lab so `docker compose up --build` starts API + worker + Postgres + Redis + Redpanda, with FastAPI `/docs` + `/health/*` and an `/admin` HTML shell based on the sample ops UI.

**Architecture:** Single FastAPI process serves OpenAPI docs, health routes, and static Admin UI. Docker Compose runs real platform dependencies; no domain providers/orders yet. Worker is the same image with a heartbeat stub command.

**Tech Stack:** Python 3.12, **Poetry** (dependency management + lockfile), FastAPI, Uvicorn, pydantic-settings, pytest, pytest-asyncio, Docker Compose. W0 may use stdlib logging (structlog later).

## Global Constraints

- Specs (local disk only): `local/PRD.md` §15–16, `local/TDD.md` §7, §24, §32.
- Master plan: `docs/plans/2026-07-23-master-implementation-plan.md`.
- **Package manager: Poetry only** — do not use pip/`requirements.txt` as the primary workflow. Commit `poetry.lock`.
- Compose stack **only**: `api`, `worker`, `postgres`, `redis`, `redpanda` — no extra infra.
- `.gitignore` already exists and ignores `local/` — do not re-add `local/` to git.
- Do **not** commit mid-wave unless the user asks; at wave end **ask** before commit + changelog.
- Out of scope for W0: auth, DB models, providers, orders, IP lifecycle, wiring Admin pages to live APIs.

---

## File map (create in this wave)

```text
BrokerBridge/
├── pyproject.toml                 # Poetry project metadata + deps
├── poetry.lock                    # commit this (reproducible installs)
├── .env.example
├── Dockerfile                     # install via Poetry (--only main)
├── docker-compose.yml
├── README.md                      # poetry + compose Local Lab section
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI factory, mounts, routers
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── health.py
│   ├── core/
│   │   ├── __init__.py
│   │   └── logging.py             # minimal setup
│   ├── workers/
│   │   ├── __init__.py
│   │   └── main.py                # heartbeat stub
│   └── static/
│       └── admin/
│           ├── index.html         # from local/brokerbridge_operations_platform.html
│           └── js/
│               └── api.js         # stub fetch helper
└── tests/
    ├── __init__.py
    ├── conftest.py
    └── test_health.py
```

Existing (do not recreate): `.gitignore`, `CLAUDE.md`, `docs/plans/*`, `local/*` (gitignored).

---

### Task 1: Poetry project skeleton + settings

**Files:**
- Create: `pyproject.toml` (Poetry format)
- Create: `poetry.lock` (via `poetry lock` / `poetry install`)
- Create: `app/__init__.py`
- Create: `app/config/__init__.py`
- Create: `app/config/settings.py`
- Create: `app/core/__init__.py`
- Create: `app/core/logging.py`
- Create: `.env.example`

**Interfaces:**
- Produces: `get_settings() -> Settings` with fields below
- Consumes: env / `.env` via pydantic-settings
- Produces: Poetry env runnable via `poetry run …`

- [x] **Step 1: Ensure Poetry is available**

Run: `poetry --version`  
Expected: Poetry 1.8+ or 2.x. If missing, install via official installer (not pip as primary app deps).

- [x] **Step 2: Create Poetry project + dependencies**

Prefer:

```bash
poetry init --name brokerbridge --python "^3.12" --no-interaction
poetry add fastapi "uvicorn[standard]" pydantic-settings
poetry add --group dev pytest pytest-asyncio httpx
```

Or hand-author `pyproject.toml`:

```toml
[tool.poetry]
name = "brokerbridge"
version = "0.1.0"
description = "Broker Network Gateway & Static IP Orchestrator"
authors = ["BrokerBridge"]
readme = "README.md"
packages = [{ include = "app" }]

[tool.poetry.dependencies]
python = "^3.12"
fastapi = ">=0.115.0"
uvicorn = { extras = ["standard"], version = ">=0.32.0" }
pydantic-settings = ">=2.6.0"

[tool.poetry.group.dev.dependencies]
pytest = ">=8.3.0"
pytest-asyncio = ">=0.24.0"
httpx = ">=0.27.0"

[build-system]
requires = ["poetry-core>=1.9.0"]
build-backend = "poetry.core.masonry.api"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [x] **Step 3: Implement settings**

```python
# app/config/settings.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    app_name: str = "BrokerBridge API"
    log_level: str = "INFO"
    docs_enabled: bool = True
    admin_ui_enabled: bool = True
    database_url: str = "postgresql+asyncpg://brokerbridge:brokerbridge@localhost:5432/brokerbridge"
    redis_url: str = "redis://localhost:6379/0"
    redpanda_brokers: str = "localhost:19092"

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [x] **Step 4: Write `.env.example` mirroring settings field names (UPPER_SNAKE via alias or document env names)**

Use env names: `APP_ENV`, `LOG_LEVEL`, `DOCS_ENABLED`, `ADMIN_UI_ENABLED`, `DATABASE_URL`, `REDIS_URL`, `REDPANDA_BROKERS`. Configure `Settings` with `Field(validation_alias=...)` or `model_config` env nested if needed so compose can inject standard names.

- [x] **Step 5: Minimal logging helper**

```python
# app/core/logging.py
import logging
import sys

def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
```

- [x] **Step 6: Install deps locally with Poetry**

Run: `poetry install`  
Expected: creates venv + installs main + dev groups; generates/updates `poetry.lock`

Sanity:

```bash
poetry run python -c "import fastapi; print(fastapi.__version__)"
```

Expected: version printed

---

### Task 2: Health API (TDD)

**Files:**
- Create: `app/api/__init__.py`
- Create: `app/api/routes/__init__.py`
- Create: `app/api/routes/health.py`
- Create: `app/api/router.py`
- Create: `app/main.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_health.py`

**Interfaces:**
- Produces: `GET /health/live` → `200` `{"status":"ok"}` (Pydantic `LiveResponse`)
- Produces: `GET /health/ready` → `200`/`503` `{"status":"ok"|"not_ready","checks":{postgres|redis|redpanda:{status,latency_ms,detail}}}` via TCP probes (`ReadyResponse`)
- Produces: centralized TDD error envelope `{error_code,message,request_id,details}` + `X-Request-ID`
- Produces: FastAPI app with docs enabled when `docs_enabled=True`

- [x] **Step 1: Write failing tests**

```python
# tests/conftest.py
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import create_app

@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

# tests/test_health.py
import pytest

@pytest.mark.asyncio
async def test_live(client):
    r = await client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

@pytest.mark.asyncio
async def test_ready(client):
    r = await client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert "checks" in body
```

- [x] **Step 2: Run tests — expect FAIL**

Run: `poetry run pytest tests/test_health.py -v`  
Expected: import/app missing failures

- [x] **Step 3: Implement health routes + app factory**

```python
# app/api/routes/health.py
from fastapi import APIRouter

router = APIRouter(tags=["health"])

@router.get("/health/live")
async def live():
    return {"status": "ok"}

@router.get("/health/ready")
async def ready():
    # W0: no DB ping yet — report degraded placeholders; W1 wires real checks
    checks = {"postgres": "skipped", "redis": "skipped", "redpanda": "skipped"}
    return {"status": "degraded", "checks": checks}
```

```python
# app/main.py
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.config.settings import get_settings
from app.core.logging import setup_logging
from app.api.router import api_router

def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.include_router(api_router)
    if settings.admin_ui_enabled:
        admin_dir = Path(__file__).parent / "static" / "admin"
        if admin_dir.exists():
            app.mount("/admin", StaticFiles(directory=admin_dir, html=True), name="admin")
    @app.get("/")
    async def root():
        return RedirectResponse(url="/admin" if settings.admin_ui_enabled else "/docs")
    return app

app = create_app()
```

Wire `api_router` to include health router.

- [x] **Step 4: Run tests — expect PASS**

Run: `poetry run pytest tests/test_health.py -v`  
Expected: PASS

---

### Task 3: Admin static shell

**Files:**
- Create: `app/static/admin/index.html` (copy from `local/brokerbridge_operations_platform.html`)
- Create: `app/static/admin/js/api.js`
- Modify: `app/static/admin/index.html` — ensure visible link to `/docs`

**Interfaces:**
- Produces: `GET /admin/` → HTML 200
- Consumes: sample HTML UX baseline on disk under `local/` (not committed)

- [x] **Step 1: Copy prototype HTML into `app/static/admin/index.html`**

Run: `cp local/brokerbridge_operations_platform.html app/static/admin/index.html`

- [x] **Step 2: Add stub API helper**

```javascript
// app/static/admin/js/api.js
window.BrokerBridgeApi = {
  baseUrl: "/api/v1",
  getToken() { return localStorage.getItem("bb_token"); },
  async request(path, options = {}) {
    const headers = Object.assign({"Content-Type": "application/json"}, options.headers || {});
    const token = this.getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(this.baseUrl + path, Object.assign({}, options, { headers }));
    return res;
  }
};
```

Include script tag in `index.html` if not already present. Add a clear **API Docs** control linking to `/docs` (new tab) in the top bar or sidebar if missing.

- [x] **Step 3: Smoke test with TestClient** (optional small test)

```python
def test_admin_index():
    from fastapi.testclient import TestClient
    from app.main import create_app
    client = TestClient(create_app())
    r = client.get("/admin/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
```

- [x] **Step 4: Run admin/health tests — expect PASS**

Run: `poetry run pytest -q`  
Expected: PASS

---

### Task 4: Worker stub

**Files:**
- Create: `app/workers/__init__.py`
- Create: `app/workers/main.py`

**Interfaces:**
- Produces: `python -m app.workers.main` loops forever, logs heartbeat every 30s

- [x] **Step 1: Implement worker**

```python
# app/workers/main.py
import logging
import time
from app.core.logging import setup_logging
from app.config.settings import get_settings

logger = logging.getLogger("brokerbridge.worker")

def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("worker_started env=%s", settings.app_env)
    while True:
        logger.info("worker_heartbeat")
        time.sleep(30)

if __name__ == "__main__":
    main()
```

- [x] **Step 2: Manual smoke** — run briefly, confirm log line, Ctrl+C (no automated test required in W0)

---

### Task 5: Docker Local Lab

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Modify: `README.md` — Local Lab URLs and commands

**Interfaces:**
- Produces: compose stack healthy enough for demo; API on `:8000`

- [x] **Step 1: Write Dockerfile (Poetry, main deps only)**

```dockerfile
FROM python:3.12-slim

ENV POETRY_VERSION=2.1.1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

COPY pyproject.toml poetry.lock README.md ./
RUN poetry install --only main --no-ansi --no-root

COPY app ./app
RUN poetry install --only main --no-ansi

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Notes:
- Copy **`README.md`** with the Poetry files — `poetry install` (with root) requires the readme path from `pyproject.toml`.
- `POETRY_VIRTUALENVS_CREATE=false` installs into the image system env (simple for containers).
- Always copy **`poetry.lock`** so builds are reproducible.
- Dev deps (`pytest`, etc.) are **not** installed in the image (`--only main`).
- Local runs use `poetry run uvicorn …` / `poetry run pytest`.

- [x] **Step 2: Write `docker-compose.yml`**

Services:
- `postgres`: `postgres:16-alpine`, user/pass/db `brokerbridge`, port `5432`
- `redis`: `redis:7-alpine`, port `6379`
- `redpanda`: official redpanda image, Kafka API on `19092` (or `9092` internal)
- `api`: build `.`, depends_on postgres/redis/redpanda, ports `8000:8000`, env `DATABASE_URL`, `REDIS_URL`, `REDPANDA_BROKERS`, healthcheck `curl -f http://localhost:8000/health/live`
- `worker`: same image, command `python -m app.workers.main`

Use a single Docker network. Prefer healthchecks so API starts after deps are up.

- [x] **Step 3: Update README**

Document local Poetry workflow + Compose:

```bash
# Local (without full compose stack for unit tests)
poetry install
poetry run pytest
poetry run uvicorn app.main:app --reload --port 8000

# Full Local Lab
docker compose up --build
```

| Surface | URL |
|---|---|
| Admin | http://localhost:8000/admin |
| Swagger | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| Live | http://localhost:8000/health/live |

- [x] **Step 4: Bring stack up**

Run: `docker compose up --build -d`  
Expected: containers running; `curl -s localhost:8000/health/live` → `{"status":"ok"}`  
Expected: `curl -s -o /dev/null -w "%{http_code}" localhost:8000/docs` → `200`  
Expected: `curl -s -o /dev/null -w "%{http_code}" localhost:8000/admin/` → `200`

- [ ] **Step 5: Tear down when done testing**

Run: `docker compose down` (optional)

---

### Task 6: Wave verification + handoff

- [x] **Step 1: Run full pytest**

Run: `poetry run pytest -q`  
Expected: all PASS

- [x] **Step 2: Mark Wave 0 complete in master plan** (`docs/plans/2026-07-23-master-implementation-plan.md` checkbox)

- [ ] **Step 3: Prepare changelog draft** (do not commit yet)

Fill mentally / draft `docs/changelogs/WAVE-00.md` from `docs/changelogs/TEMPLATE.md`.

- [ ] **Step 4: Ask user**

> Wave 0 tested (pytest + compose smoke). Commit and update changelog?

- [ ] **Step 5: On approval only** — commit + update `CHANGELOG.md` + `docs/changelogs/WAVE-00.md` (who/where/why/what from git)

---

## Testing

Wave 0 verification has three layers. Run them in order after implementation (or when re-verifying the foundation).

### 1. Unit / API tests (Poetry)

```bash
poetry install   # if needed
poetry run pytest -q
```

Expected: all tests PASS (health live/ready schema + 503 path + error envelope + admin HTML).

- [x] `poetry run pytest -q` passes

### 2. Compose smoke (curl)

```bash
docker compose up --build -d
curl -sS http://localhost:8000/health/live    # → 200 {"status":"ok"}
curl -sS -w "\n%{http_code}\n" http://localhost:8000/health/ready
# → 200 {"status":"ok","checks":{...}} when deps up
# → 503 {"status":"not_ready","checks":{...}} when any critical check fails
# each check: {status, latency_ms, detail} — OpenAPI models (not additionalProp1)
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8000/docs     # → 200
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8000/redoc    # → 200
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8000/admin/   # → 200 HTML
docker compose ps   # api healthy; worker/postgres/redis/redpanda up
```

- [x] Compose stack healthy; health/docs/redoc/admin curl smoke PASS
- [x] Re-verify ready `200` vs `503` + structured checks after health-contract hardening

### 3. Web UI smoke via Chrome DevTools MCP

When the **Chrome DevTools MCP** server (`plugin-chrome-devtools-mcp-chrome-devtools`) is available:

1. Discover tools with `GetMcpTools` for that server.
2. Open/navigate `http://localhost:8000/admin/` and `http://localhost:8000/docs`.
3. Assert each page loads (title / visible content: Admin shell title contains `BrokerBridge`; Swagger UI loads).
4. Optionally capture a screenshot and note any console errors (CDN/font noise is acceptable in W0; hard JS failures are not).

If MCP is unavailable, in `error` state, or `mcp_auth` fails/times out: **skip this layer**, fall back to compose curl smoke above, and document the skip reason in the verification handoff.

- [ ] Chrome DevTools MCP: `/admin` loads (title/content)
- [ ] Chrome DevTools MCP: `/docs` loads (Swagger UI)
- [ ] Chrome DevTools MCP: console checked (or noted N/A)
- [x] DevTools skipped with reason documented (if MCP unavailable) — *2026-07-23: serverStatus=error; mcp_auth timed out; curl smoke used instead*

---

## Definition of Done

- [x] `poetry install` works; `poetry.lock` present (commit with the wave on user approval)
- [x] `docker compose up --build` starts api, worker, postgres, redis, redpanda
- [x] `GET /health/live` → 200 `ok` (`LiveResponse` in OpenAPI)
- [x] `GET /health/ready` → structured checks; `200` when all TCP probes ok, `503` + `not_ready` otherwise
- [x] Centralized error envelope + `X-Request-ID` middleware (validation / AppError / unhandled)
- [x] `/docs` and `/redoc` load
- [x] `/admin/` serves HTML shell (prototype data OK)
- [x] `poetry run pytest` passes
- [x] README documents Poetry + Local Lab URLs
- [x] Compose curl smoke for health/docs/admin (see Testing)
- [x] Web UI smoke via Chrome DevTools MCP for `/admin` + `/docs` when MCP is available; otherwise curl fallback documented
- [ ] User offered commit + changelog

## Out of Scope (explicit)

- JWT/login wiring, provider framework, SQLAlchemy models, Alembic
- Order/broker/IP APIs
- Replacing Admin mock charts with live metrics
- Vultr / real brokers
- Pushing to remote
- Using pip/`requirements.txt` as the primary dependency workflow

## Next wave

After W0 commit: create/execute **Wave 1** plan — Data + Providers + Auth (`docs/plans/WAVE-1-data-providers-auth.md`).
