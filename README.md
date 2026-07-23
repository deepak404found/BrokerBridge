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

# API only (no full compose stack)
poetry run uvicorn app.main:app --reload --port 8000
```

Copy `.env.example` to `.env` if you want local overrides.

## Status

Wave 0 Local Lab foundation is up (`docker compose up --build`, `/admin`, `/docs`, health).  
**Next:** Wave 1 after W0 commit — see master plan.

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

## Wave workflow

1. Implement wave plan → test  
2. Ask before commit  
3. On approval: commit + update `CHANGELOG.md` + `docs/changelogs/WAVE-XX.md`
