# Interviewer demo checklist (Part 24 / Wave 6)

## Boot Local Lab (database mock — default)

```bash
docker compose up --build
# Admin http://localhost:8000/admin
# Swagger http://localhost:8000/docs
```

Login: seed admin from `.env` (`SEED_ADMIN_*`).

## Walkthrough

1. **Runtime Config** — Infrastructure shows `mock` + `mock_backend=database` badge.
2. **Instances + Static IPs** — sidebar **Instances** (provision / suspend / destroy). **Static IPs** for allocate → assign → attach. KPI cards are clickable: filter the table; click the same KPI again to clear. **Running Instances** KPI on Static IPs navigates to Instances (does not filter the IP table).
3. **Orders** — place buy; Event Bus shows `order.submitted` after drain. Status KPIs filter the order list (toggle clear).
4. **Subscriptions (Clients)** — create subscription → Expire → confirm orders return `SUBSCRIPTION_EXPIRED`. Active / Expired KPIs filter the table.
5. **Vultr plug-in (fake key)** — Runtime Config → `vultr` + garbage `api_key` → Validate fails with `PROVIDER_VALIDATION_FAILED`; prior mock remains; secrets stay masked (`***`).
6. **Swagger** — try `/api/v1/subscriptions` and `/api/v1/infrastructure/instances/{id}/suspend`.
7. **Dashboard pills** — session / IP / health / engine status pills navigate to the matching page with an optional filter seed.

## Optional docker mock realism

Socket is mounted in default `docker compose up`. Activate `mock_backend=docker` in Runtime Config
(or use the overlay to force docker at cold start):

```bash
docker compose -f docker-compose.yml -f docker-compose.docker-infra.yml up --build
./scripts/w6_compose_e2e_docker.sh
```

Suspend/start an instance and confirm status flips (containers labeled `brokerbridge.mock=1`).
If Docker Engine is unavailable, Admin shows a degradation banner and falls back to `database`.
## Optional light load

Honest Local Lab recipe (not a 5k/min claim):

```bash
# 60s sustained buys against Local Lab (requires assigned IP + active subscription/none)
hey -z 60s -q 20 -m POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"client_id":"…","client_order_id":"load-1","symbol":"AAPL","quantity":1}' \
  http://localhost:8000/api/v1/orders/buy
```

Or use `ab` / Locust against `/health/live` for a safe smoke. Record observed RPS honestly in demos.

## E2E scripts

```bash
./scripts/w6_compose_e2e_database.sh   # required
./scripts/w6_compose_e2e_docker.sh     # skip OK if no socket
```
