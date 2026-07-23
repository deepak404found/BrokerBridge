# BrokerBridge Master Implementation Plan

> **For agentic workers:** Execute **one wave at a time**. Before coding a wave, ensure a wave-specific plan exists under `docs/plans/`. After a wave is tested, **ask the user before committing**, then update `CHANGELOG.md` + `docs/changelogs/WAVE-XX.md` per project rules.

**Goal:** Ship a production-grade Broker Network Gateway (BrokerBridge) that demos all 24 assignment parts via Local Lab (`docker compose up`), Admin UI (`/admin`), and Swagger (`/docs`), with mock providers by default and optional real providers via runtime config.

**Architecture:** Modular monolith (FastAPI + workers), provider-based adapters, Clean Architecture layers, PostgreSQL / Redis / Redpanda. Specs: `local/PRD.md` v2.3, `local/TDD.md` v2.3.

**Tech Stack:** Python 3.12, Poetry, FastAPI, SQLAlchemy 2 + Alembic, Pydantic v2, Redis, Redpanda, pytest, Docker Compose, Render (prod).

## Global Constraints

- Follow `CLAUDE.md` and `.cursor/rules/*` always.
- Dependency order from TDD §30 — **not** Part 1→24 linear.
- Local Lab: mocks default; no Vultr/broker secrets required for demos.
- Domain never imports Vultr/Redis/Kafka/broker SDKs directly — providers only.
- Admin = FastAPI-hosted HTML (sample UX); no Next.js in v1.
- Swagger `/docs` + ReDoc must stay enabled for demos.
- After each wave: **test → ask user to commit → changelog** (who/where/why/what).

## Source of Truth

| Doc | Path |
|---|---|
| PRD | `local/PRD.md` |
| TDD | `local/TDD.md` |
| Admin UX prototype | `local/brokerbridge_operations_platform.html` |
| Wave changelog template | `docs/changelogs/TEMPLATE.md` |

---

## Waves Overview

| Wave | Name | TDD phases | Demo when done |
|---|---|---|---|
| **W0** | Foundation / Local Lab | 0, 0b | Compose up; `/docs`; `/admin` shell; health |
| **W1** | Data + Providers + Auth | 1, 2, 2b, 3 | DB + provider framework + JWT login |
| **W2** | Brokers + Sessions + IP/Infra | 4–8 | Brokers, sessions, mock IP lifecycle, locks, whitelist |
| **W3** | Health + Limits + Routing + Orders | 9–13 | Buy/sell/cancel; routing; basic failover |
| **W4** | Rotation + Regions + Events | 14–16 | Zero-downtime rotate; multi-region; Redpanda events |
| **W5** | Replay + Monitor + Sim + Config UI | 17–20 | Replay, dashboard, chaos sim, provider hot-swap UI |
| **W6** | Vultr + Expiry + Polish | 21–24 | Optional Vultr; subscription teardown; load test; Render guide |

**Rule:** Do not start Wave N+1 until Wave N Definition of Done is met and user has been offered a commit + changelog update.

---

## Wave Definition of Done (all waves)

- [ ] Unit/integration tests for new behavior pass
- [ ] Local Lab still boots (`docker compose up`)
- [ ] New capability visible in `/admin` and/or `/docs`
- [ ] No secrets in logs; providers still abstracted
- [ ] Wave plan checkboxes updated
- [ ] User asked: commit? → on yes: commit + changelog entry

---

## Wave Plans

| Wave | Plan file |
|---|---|
| W0 | `docs/plans/2026-07-23-wave-0-foundation.md` ✅ completed + committed |
| W1 | `docs/plans/WAVE-1-data-providers-auth.md` ✅ completed + committed |
| W2 | `docs/plans/WAVE-2-brokers-sessions-ip.md` *(create before start)* |
| W3 | `docs/plans/WAVE-3-routing-orders.md` *(create before start)* |
| W4 | `docs/plans/WAVE-4-rotation-events.md` *(create before start)* |
| W5 | `docs/plans/WAVE-5-ops-replay-sim-config.md` *(create before start)* |
| W6 | `docs/plans/WAVE-6-vultr-polish.md` *(create before start)* |

---

## Execution Protocol (agents)

1. Read PRD/TDD sections relevant to the wave.
2. Open or create the wave plan; implement task-by-task.
3. Run tests; smoke Admin/Swagger.
4. **Stop and ask user to approve commit.**
5. On approval: commit (user rules HEREDOC style) + append changelog (see rules).
6. Mark wave complete in this master plan.

### Master progress

- [x] W0 Foundation
- [x] W1 Data + Providers + Auth
- [ ] W2 Brokers + Sessions + IP
- [ ] W3 Routing + Orders
- [ ] W4 Rotation + Events
- [ ] W5 Ops + Replay + Sim + Config
- [ ] W6 Vultr + Polish

---

## Interviewer demo path (target after W5)

1. `docker compose up --build`
2. Open `/admin` → login
3. Brokers → Orders → Static IPs → Runtime Config → Simulator
4. Open `/docs` for API try-it-out
5. Optional: `docker compose stop redis` then recover

---

## Document Control

| Version | Date | Notes |
|---|---|---|
| 1.0 | 2026-07-23 | Initial master plan from PRD/TDD v2.3 |
