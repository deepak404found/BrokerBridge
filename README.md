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

Copy `.env.example` to `.env` if you want local overrides.

**Dev admin (seeded on startup):** `admin@brokerbridge.local` / `admin123!`  
Login via Swagger `POST /api/v1/auth/token` (username = email) or the Admin JWT panel.

## Status

Wave 0 foundation + Wave 1 (DB, providers, JWT) are implemented.  
**Next:** Wave 2 — Brokers + Sessions + IP/Infra.

## Local Lab (Docker Compose)

```bash
docker compose up --build
# or detached:
docker compose up --build -d
```

| Surface | URL |
|---|---|
| Admin | http://localhost:8000/admin |
| Swagger | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| Live | http://localhost:8000/health/live |
| Ready | http://localhost:8000/health/ready |

Stack services: `api`, `worker`, `postgres`, `redis`, `redpanda`.

Startup creates schema (`create_all`) and seeds mock providers + admin user. Alembic migration `001_initial` is also available for prod-style upgrades.

## Wave workflow

1. Implement wave plan → test  
2. Ask before commit  
3. On approval: commit + update `CHANGELOG.md` + `docs/changelogs/WAVE-XX.md`
