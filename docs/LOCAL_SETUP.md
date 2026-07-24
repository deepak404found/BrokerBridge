# Local Lab setup (Docker Compose)

**Preferred way to run BrokerBridge.** Local Lab brings up the full stack so demos match the architecture: API, worker, Postgres, Redis, and Redpanda. This is more complete and realistic than the cloud Render demo (which cannot mount a Docker socket and often uses an in-process event bus if Redpanda is unreachable).

## Prerequisites

- Docker Engine + Docker Compose v2
- Copy env and fill placeholders (never commit `.env`):

```bash
cp .env.example .env
```

For Compose, keep service hostnames in URLs (`postgres`, `redis`, `redpanda`) as in `.env.example`.

## Start the stack

```bash
docker compose up --build
# detached:
docker compose up --build -d
```

| Service | Role |
|---|---|
| `api` | FastAPI + Admin static + Swagger |
| `worker` | Outbox drain + event consumer |
| `postgres` | System of record |
| `redis` | Locks, sessions, rate limits |
| `redpanda` | Kafka-compatible event bus |

Default cold-start infra: `INFRA_PROVIDER=mock`, `MOCK_INFRA_BACKEND=database`. Compose mounts `/var/run/docker.sock` so you can later **Admin-activate** `mock_backend=docker` without a separate file (trusted machines only).

### Optional: force docker mock at cold start

```bash
docker compose -f docker-compose.yml -f docker-compose.docker-infra.yml up --build
```

If DB still has an active docker backend but the socket is missing, the API falls back to `database` and Admin shows a degradation banner.

## URLs

| Surface | URL |
|---|---|
| Admin | http://localhost:8000/admin |
| Swagger | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| Live | http://localhost:8000/health/live |
| Ready | http://localhost:8000/health/ready |

**Login:** `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` from your `.env` (seeded on startup).

## Why Local Lab vs Render

| Capability | Local Compose | Render |
|---|---|---|
| Postgres + Redis | Yes | Managed (e.g. Upstash Redis) |
| Redpanda in-stack | Yes | External / may fail → use **memory** in Runtime Config |
| `mock_backend=docker` | Yes (socket) | No — use **database** only |
| Redis stop chaos | `docker compose stop redis` | Not via compose |
| Admin static updates | `docker compose up --build -d api` | Redeploy image |

## Poetry / uvicorn only (optional)

Useful for unit tests or API-only work; **not** a full Local Lab:

```bash
poetry install
poetry run pytest -q
poetry run uvicorn app.main:app --reload --port 8000
```

Without Compose you must point `DATABASE_URL` / `REDIS_URL` / brokers at reachable services yourself. Prefer Compose for demos.

## Migrations, tests, E2E

Startup runs schema `create_all` for Local Lab convenience. For Alembic-style upgrades:

```bash
poetry run alembic upgrade head
```

```bash
poetry run pytest -q
./scripts/w6_compose_e2e_database.sh    # mock database path
./scripts/w6_compose_e2e_docker.sh      # needs Docker Engine; skip if unavailable
```

## Resilience demos

```bash
docker compose stop redis   # /health/ready → 503; Admin Dashboard shows redis fail
docker compose start redis  # recovers
```

With Redis down, lock / session / rate-limit paths return `REDIS_UNAVAILABLE` (503).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Admin UI looks old after a pull | `docker compose up --build -d api worker` then hard-refresh (static is baked into the image; plain `restart` is not enough) |
| Port 8000 in use | Stop the other process or change the published port in Compose |
| Docker probe / instances fail | Switch Runtime Config to `mock_backend=database`, or ensure the socket is mounted |
| Opaque provider errors | Rebuild to latest Admin toast/`formatError` and read the API `message` |
| Event Bus empty | Confirm Redpanda is up, or activate **memory** under Runtime Config → Event Bus |

Next: exercise features with [DEMO.md](DEMO.md). Architecture: [ARCHITECTURE.md](ARCHITECTURE.md).
