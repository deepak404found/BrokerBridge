# Wave Changelog — WAVE-00

## Metadata

| Field | Value |
|---|---|
| **Wave** | W0 |
| **Title** | Foundation / Local Lab |
| **Plan** | `docs/plans/2026-07-23-wave-0-foundation.md` |
| **Status** | completed |
| **When** | 2026-07-23 |
| **Who** | deepak404found |
| **Where** | branch `main` `c2d8a5e` |
| **Why** | Establish runnable Local Lab so all later waves can demo against Compose, Admin, and Swagger without cloud dependencies |

## What changed

### Features / behavior

- Poetry-based Python 3.12 project with lockfile
- FastAPI app with `/docs`, `/redoc`, OpenAPI
- Liveness `/health/live` and readiness `/health/ready` with TCP probes for postgres/redis/redpanda
- Ready returns `200`/`ok` or `503`/`not_ready` with structured `CheckResult` payloads
- Centralized error envelope + `X-Request-ID` middleware and exception handlers
- Operations Admin HTML shell at `/admin` (from prototype UX)
- Worker heartbeat stub
- Docker Compose Local Lab: api, worker, postgres, redis, redpanda

### APIs / Admin / Swagger

- `GET /health/live` → `LiveResponse`
- `GET /health/ready` → `ReadyResponse` (200 / 503)
- Error schemas for validation / AppError / internal errors
- `/admin/` static UI + link to `/docs`

### Files (high level)

- Created: `pyproject.toml`, `poetry.lock`, `app/**`, `tests/**`, `Dockerfile`, `docker-compose.yml`, `.env.example`
- Modified: `README.md`, wave/master plans

### Tests

- Commands run: `poetry run pytest -q`
- Results: **10 passed**

### How verified (Local Lab)

- [x] `docker compose up --build`
- [x] `/admin` → 200 HTML
- [x] `/docs` → 200 Swagger
- [x] `/health/live` + `/health/ready` curl smoke
- [ ] Chrome DevTools MCP (unavailable; curl fallback documented)

## Notes / follow-ups

- Out of scope deferred to W1: DB models, Alembic, provider framework, JWT auth, Admin login wiring
- Readiness uses TCP probes in W0 (full client drivers come with later waves as needed)
