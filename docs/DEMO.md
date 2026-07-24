# Demo and testing

How to run and exercise BrokerBridge after setup. Local Lab setup: [LOCAL_SETUP.md](LOCAL_SETUP.md). Cloud deploy notes: [deploy/RENDER.md](deploy/RENDER.md).

## Credentials

| Environment | URL | Login |
|---|---|---|
| Local Lab | http://localhost:8000/admin | `SEED_ADMIN_*` from your `.env` |
| Cloud | https://brokerbridge.onrender.com/admin | `admin@example.com` / `admin@404` |

The Admin login page may show a Local Lab seed hint; that hint does **not** apply to the cloud demo — use the cloud credentials above.

---

## Local Lab path (full stack)

Prereq: [LOCAL_SETUP.md](LOCAL_SETUP.md) (`docker compose up --build`).

1. **Runtime Config** — Infrastructure `mock` + `database` (or activate `docker` if the socket is available). Event bus should reach Compose Redpanda (or activate memory if needed).
2. **Clients** — Create subscription (ACTIVE covering `starts`–`ends`).
3. **Instances** — Provision Instance.
4. **Static IPs** — Allocate → Assign to an enabled broker → Attach to the instance.
5. **Orders** — Paste/copy client UUID into Client ID → Buy → expect SUBMITTED.
6. **Event Bus** — Reload / Drain; look for `order.submitted` / IP events. KPI filters toggle.
7. **Clients** — Expire → Buy should return `SUBSCRIPTION_EXPIRED` → Create subscription → Buy again.
8. **Chaos** — Enable a fault briefly; confirm live APIs degrade; Clear all; Audit updates.
9. **Redis chaos** — `docker compose stop redis` → Dashboard ready / redis fail → `start redis`.
10. **Swagger** — Authorize with token; try subscriptions or instance suspend.

Optional docker realism:

```bash
docker compose -f docker-compose.yml -f docker-compose.docker-infra.yml up --build
./scripts/w6_compose_e2e_docker.sh
```

---

## Cloud (Render) path

Infra must stay **`mock` / `database`** (no Docker socket).

1. Login with cloud credentials.
2. **Runtime Config** — confirm mock/database. If Event provider is missing or Redpanda health fails (`not_ready`), **Validate & activate** event provider **`memory`** so Event Bus can show rows.
3. If tables are empty, fill via Admin mutate (no special seed):
   - Create subscription → Provision instance → Allocate / Assign / Attach IP → Buy.
4. Walk Dashboard, Brokers, Health, Rate Limits, Sessions, Clients, Instances, Static IPs, Orders, Event Bus.
5. Expect `/health/ready` to stay **not_ready** while Redpanda/Kafka bootstrap is unreachable even if pg/redis are ok — that is an env wiring issue, not a missing Admin feature.

---

## Swagger spot-checks

1. Open `/docs` → Authorize (password flow; username = email).
2. `GET /api/v1/brokers`, `GET /api/v1/subscriptions`.
3. `POST /api/v1/orders/buy` with covering client + assigned IP broker context as required by policy.
4. `POST /api/v1/infrastructure/instances/{id}/suspend` when an instance exists.

---

## Light load (honest)

Not a fixed 5k/min claim. With assigned IP + ACTIVE subscription:

```bash
# Example — unique client_order_id per request
hey -z 60s -q 20 -m POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"client_id":"…","client_order_id":"load-1","symbol":"AAPL","quantity":1}' \
  http://localhost:8000/api/v1/orders/buy
```

Watch Dashboard KPIs and `/health/ready`. Prefer Local Lab Redpanda or memory event provider during the run.
