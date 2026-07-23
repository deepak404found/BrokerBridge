# BrokerBridge — Agent Guide (CLAUDE.md)

This repository implements **BrokerBridge**: a production-grade Broker Network Gateway & Static IP Orchestrator (Senior Python assignment).

## Specs (read first)

| Doc | Path |
|---|---|
| PRD | `local/PRD.md` (v2.3) |
| TDD | `local/TDD.md` (v2.3) |
| Master plan | `docs/plans/2026-07-23-master-implementation-plan.md` |
| Admin UX prototype | `local/brokerbridge_operations_platform.html` |

Do not contradict PRD/TDD without explicit user approval.

## Architecture non-negotiables

1. **Provider-based** — domain/services never import Vultr, Redis clients, Kafka clients, or broker SDKs directly.
2. **Local Lab first** — `docker compose up` must demo features with **mock** providers; real Vultr/brokers optional via runtime config.
3. **Modular monolith** — FastAPI + workers; not microservices theater.
4. **Async-first** Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2.
5. **Admin UI** — FastAPI-hosted HTML under `app/static/admin` (not Next.js in v1).
6. **Swagger** — keep `/docs` and `/redoc` enabled for demos.

## Delivery process (waves)

Work in waves **W0→W6** (see master plan). For each wave:

1. Create/follow `docs/plans/…` wave plan.
2. Implement + test (pytest + Admin/Swagger smoke).
3. **Ask the user before committing.**
4. On approval: git commit + update changelog (who / where / why / what).

Never commit secrets (`.env`, API keys, Vultr tokens).

## Changelog & commits

See `.cursor/rules/wave-changelog-commits.mdc`.

- Root log: `CHANGELOG.md` (Keep a Changelog style)
- Per-wave detail: `docs/changelogs/WAVE-XX.md` from `docs/changelogs/TEMPLATE.md`

## Code quality bar

- Type hints on public functions; explicit error envelopes for APIs.
- Tests for new domain behavior before or with implementation.
- Structured JSON logging; never log secrets.
- Small, focused PRs/commits per wave when user approves.

## Commands (target)

```bash
docker compose up --build
pytest -q
# Admin http://localhost:8000/admin
# Swagger http://localhost:8000/docs
```
