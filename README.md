# BrokerBridge

**Broker Network Gateway & Static IP Orchestrator** — route orders through brokers that require fixed egress IPs, with provider-based infrastructure (mock or Vultr), sessions, rate limits, events, and an Operations Admin UI.

Domain code never imports Vultr, Redis, Kafka, or broker SDKs directly; adapters sit behind provider interfaces and can be hot-swapped from Admin **Runtime Config**.

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| API | FastAPI + Pydantic v2 |
| ORM / DB | SQLAlchemy 2 + PostgreSQL (asyncpg) |
| Cache / locks / sessions / rate limits | Redis |
| Events | Redpanda / Kafka-compatible (or in-process memory) |
| Workers | Async outbox drain + event consumer |
| Local Lab | Docker Compose (`api`, `worker`, `postgres`, `redis`, `redpanda`) |
| Admin | FastAPI-hosted HTML (`/admin`) |
| API docs | Swagger `/docs`, ReDoc `/redoc` |

## Demo URLs

| Environment | Admin | Swagger | ReDoc |
|---|---|---|---|
| **Cloud** | [https://brokerbridge.onrender.com/admin](https://brokerbridge.onrender.com/admin) | [/docs](https://brokerbridge.onrender.com/docs) | [/redoc](https://brokerbridge.onrender.com/redoc) |
| **Local Lab** | http://localhost:8000/admin | http://localhost:8000/docs | http://localhost:8000/redoc |

**Cloud login (demo):** `admin@example.com` / `admin@404`  
**Local Lab login:** values from your `.env` (`SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD`; see `.env.example`).

Local Docker Compose is the **most complete** demo (real Redpanda in the stack, Redis stop/recover, optional docker-backed mock instances). Render uses mock infra **`database`** only (no Docker socket).

## Quick start (Local Lab)

```bash
cp .env.example .env   # fill placeholders — never commit .env
docker compose up --build
```

Open Admin and Swagger at the Local Lab URLs above. Full setup, optional docker mock infra, pytest, and troubleshooting: **[docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md)**.

## Test (summary)

1. Sign in to Admin.
2. **Runtime Config** — confirm infra `mock` (Local: `database` or `docker`; Render: `database`).
3. **Clients** — create an ACTIVE subscription (covering window).
4. **Instances** — provision; **Static IPs** — allocate → assign broker → attach.
5. **Orders** — Buy/Sell; confirm status in history.
6. **Event Bus** — drain / live feed after orders (Local Redpanda, or memory if cloud bus is down).
7. **Chaos / Redis** — Local: enable a fault or `docker compose stop redis` and watch Dashboard ready.
8. **Swagger** — authorize and try a few `/api/v1` routes.

Detailed steps: **[docs/DEMO.md](docs/DEMO.md)**.

## Documentation

| Doc | Contents |
|---|---|
| [docs/README.md](docs/README.md) | Docs index |
| [docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md) | Docker Local Lab setup |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, providers, ERD, sequences, scale |
| [docs/FEATURES.md](docs/FEATURES.md) | Features, use cases, Admin/API paths |
| [docs/DEMO.md](docs/DEMO.md) | How to run and test (Local + cloud) |
| [docs/deploy/RENDER.md](docs/deploy/RENDER.md) | Render / Upstash / Redpanda deploy notes |
| [CHANGELOG.md](CHANGELOG.md) | Release history |

## Specs

- Product: [`local/PRD.md`](local/PRD.md)
- Technical: [`local/TDD.md`](local/TDD.md)
