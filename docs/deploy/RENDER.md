# Render deploy

BrokerBridge on Render is a **modular monolith**: Web (API) + Worker, managed Postgres, managed Redis (e.g. Upstash), and an optional external Kafka/Redpanda-compatible bus.

**Local Docker Compose is the fuller / more realistic lab** (in-stack Redpanda, Redis stop demo, optional `mock_backend=docker`). See [LOCAL_SETUP.md](../LOCAL_SETUP.md). On Render, use mock infra **`database` only** — never mount a Docker socket.

## Local Lab vs Render

| Concern | Local Lab (`docker compose`) | Render |
|---|---|---|
| Infra provider | `mock` | `mock` |
| Mock backend | `database` (default) or `docker` | **`database` only** |
| Docker socket | Mounted for optional docker mock | **Never** |
| Event bus | Compose Redpanda | External cluster or **memory** via Admin |
| Redis | Compose Redis | Upstash / managed `REDIS_URL` |
| Vultr | Optional Admin activate | Optional Admin activate |

## Services

1. **Web** — image from this repo; `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
2. **Worker** — same image; `python -m app.workers.main`
3. **PostgreSQL** — managed; `DATABASE_URL=postgresql+asyncpg://…`
4. **Redis** — managed; `REDIS_URL=…` with `LOCK_PROVIDER=redis`, `SESSION_PROVIDER=redis`, `RATE_LIMIT_PROVIDER=redis`

## Required env (dashboard only — no secrets in git)

From `.env.example` patterns:

- `JWT_SECRET`, `SECRETS_FERNET_KEY`, `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD`
- `DATABASE_URL`, `REDIS_URL`
- `INFRA_PROVIDER=mock`
- `MOCK_INFRA_BACKEND=database`
- `BROKER_PROVIDER=mock`
- `EVENT_PROVIDER=memory` **or** reachable Redpanda/Kafka bootstrap (`KAFKA_*` / `REDPANDA_*`)

If Redpanda health shows `Connection refused`, Admin → Runtime Config → activate **memory** for the event provider so Event Bus and outbox demos still work. `/health/ready` may remain `not_ready` until the bus endpoint is fixed.

Leave `VULTR_API_KEY` empty in env; use Admin Runtime Config for Vultr keys (masked).

## Security

- Do not mount `/var/run/docker.sock` on Render.
- Never commit `.env` or API keys.
- Admin secrets are write-only / masked in API responses.

## After deploy

1. Open `/admin` → login with seed admin configured on Render.
2. Runtime Config → infra **mock / database**.
3. Smoke Brokers → (create subscription + IP attach if empty) → Orders → Event Bus.
4. Click-path detail: [DEMO.md](../DEMO.md).

## Migrations

API lifespan may `create_all` for convenience. Prefer:

```bash
alembic upgrade head
```

Revision `005_w6` adds `subscriptions` + `mock_infra_resources`.
