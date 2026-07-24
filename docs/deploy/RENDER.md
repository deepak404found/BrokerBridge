# Render Deploy Guide — BrokerBridge

BrokerBridge runs as a **modular monolith**: one Web (API) service + one Worker, plus managed Postgres and Redis. Event bus may be Memory (simplest) or an external Kafka/Redpanda-compatible cluster.

## Recommended Local Lab vs Render

| Concern | Local Lab (`docker compose`) | Render |
|---|---|---|
| Infra provider | `INFRA_PROVIDER=mock` | `INFRA_PROVIDER=mock` |
| Mock backend | `MOCK_INFRA_BACKEND=database` (default) | **`database` only** |
| Docker socket | Local Lab compose mounts for optional `mock_backend=docker` | **Never mount** |
| Vultr | Optional via Admin Runtime Config | Optional later (plug key in Admin) |

## Services to create

1. **Web** — Docker image from this repo; start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
2. **Worker** — same image; start `python -m app.workers.main`
3. **PostgreSQL** — managed; set `DATABASE_URL=postgresql+asyncpg://…`
4. **Redis** — managed; set `REDIS_URL=redis://…` and prefer `LOCK_PROVIDER=redis`, `SESSION_PROVIDER=redis`, `RATE_LIMIT_PROVIDER=redis`

## Required env (no secrets in git)

Copy from `.env.example` and fill in the Render dashboard:

- `JWT_SECRET`, `SECRETS_FERNET_KEY`, `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD`
- `DATABASE_URL`, `REDIS_URL`
- `INFRA_PROVIDER=mock`
- `MOCK_INFRA_BACKEND=database`
- `BROKER_PROVIDER=mock`
- `EVENT_PROVIDER=memory` (or Redpanda/Kafka brokers if you attach a bus)
- Leave `VULTR_API_KEY` empty — use Admin **Runtime Config** to validate/activate Vultr later (FR-21)

## Security notes

- Do **not** mount `/var/run/docker.sock` on Render or any shared host.
- Never commit `.env` or Vultr API keys.
- Admin secrets are write-only / masked in API responses.

## Bootstrap checklist

1. Deploy Web + Worker with the env above.
2. Open `/admin` → login with seed admin.
3. Confirm Runtime Config shows `Active: mock (database)`.
4. Smoke Brokers → Static IPs → Orders → Events.
5. Optional: Runtime Config → Vultr with a real key (paid) or confirm fake key validate fails cleanly.

## Migrations

API lifespan runs `create_all` for Local Lab convenience. For production, prefer Alembic:

```bash
alembic upgrade head
```

Revision `005_w6` adds `subscriptions` + `mock_infra_resources`.
