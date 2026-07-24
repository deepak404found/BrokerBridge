# BrokerBridge

Production-oriented **Broker Network Gateway & Static IP Orchestrator** (working name).

## Specs & plans

- Product: [`local/PRD.md`](local/PRD.md)
- Technical: [`local/TDD.md`](local/TDD.md)
- Master plan: [`docs/plans/2026-07-23-master-implementation-plan.md`](docs/plans/2026-07-23-master-implementation-plan.md)
- Agent guide: [`CLAUDE.md`](CLAUDE.md)
- Changelog: [`CHANGELOG.md`](CHANGELOG.md)

## Local development (Poetry)

```bash
# Install (creates venv + uses poetry.lock)
poetry install

# Unit tests
poetry run pytest -q

# API only (no full compose stack; needs Postgres for real DB, or use compose)
poetry run uvicorn app.main:app --reload --port 8000

# Optional: apply Alembic migrations against DATABASE_URL
poetry run alembic upgrade head
```

Copy `.env.example` to `.env` and replace the placeholders with Local Lab values
(`.env` is gitignored — never commit it). Compose loads `.env` for postgres
`${POSTGRES_*}` substitution and as `env_file` for `api` / `worker` — do not put
secrets or connection strings inline in `docker-compose.yml`.

**Dev admin (seeded on startup with Local Lab defaults):** `admin@brokerbridge.local` / `admin123!`  
Login via Swagger `POST /api/v1/auth/token` (username = email) or the Admin JWT panel.

## Status

Waves 0–4 are implemented (Local Lab through IP rotation, outbox events, and Admin Event Bus).  
**Next:** Wave 5 — Replay + Monitor + Sim + Config UI (includes EventProvider consumer).

## Local Lab (Docker Compose)

```bash
docker compose up --build
# or detached:
docker compose up --build -d
```

| Surface | URL |
|---|---|
| Admin | http://localhost:8000/admin |
| Swagger | http://localhost:8000/docs (Authorize persists after refresh) |
| ReDoc | http://localhost:8000/redoc |
| Live | http://localhost:8000/health/live |
| Ready | http://localhost:8000/health/ready |

Stack services: `api`, `worker`, `postgres`, `redis`, `redpanda`.

Local Lab defaults (`.env.example`): `LOCK_PROVIDER=redis`, `SESSION_PROVIDER=redis`,
`RATE_LIMIT_PROVIDER=redis`. Pytest forces Memory via `tests/conftest.py`. Cache stays
in-process Memory. Resilience demo:

```bash
docker compose stop redis   # /health/ready → 503; Admin READY shows redis fail
docker compose start redis  # ready recovers; Admin banner clears on auto-refresh
```

When Redis is down, rate-limit / session-ensure / IP-lock paths return
`REDIS_UNAVAILABLE` (503). Dashboard still loads and surfaces redis `fail` + rate-limit
unavailable note.

Startup creates schema (`create_all`) and seeds mock providers + admin user. Alembic migration `001_initial` is also available for prod-style upgrades.

## Wave workflow

1. Implement wave plan → test  
2. Ask before commit  
3. On approval: commit + update `CHANGELOG.md` + `docs/changelogs/WAVE-XX.md`
