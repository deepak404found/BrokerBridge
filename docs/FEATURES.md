# Features

Map of product capabilities to Admin and APIs. Spec detail: [`local/PRD.md`](../local/PRD.md).

## Feature map

| Feature | Admin | Primary APIs |
|---|---|---|
| Login / RBAC | Sign-in gate | `POST /api/v1/auth/token` |
| Dashboard | Dashboard | `/api/v1/monitoring/*`, `/health/*` |
| Brokers | Brokers | `/api/v1/brokers` |
| Smart routing | Smart Routing | routing weights / preview |
| Orders | Orders | `/api/v1/orders/*` |
| Sessions | Sessions | sessions / ensure |
| Broker health | Broker Health | `/api/v1/monitoring/brokers/health` |
| Rate limits | Rate Limits | `/api/v1/monitoring/rate-limits` |
| Static IPs | Static IPs | `/api/v1/infrastructure/ips*` |
| Instances | Instances | `/api/v1/infrastructure/instances*` |
| Subscriptions | Clients | `/api/v1/subscriptions` |
| Event bus | Event Bus | events + WS; outbox drain |
| Replay | Replay | `/api/v1/admin/replay/*` |
| Chaos | Chaos Simulator | `/api/v1/admin/failure-sim/*` |
| Runtime config | Runtime Config | `/api/v1/admin/providers/*`, config items |
| Audit (sim) | Audit Logs | simulator toggle history |

KPI cards on list pages are **clickable filters** (click again to clear). Static IPs **Running Instances** KPI navigates to **Instances**.

---

## Gateway, routing, and orders

**Use cases:** Onboard mock brokers; score candidates; place inline buy/sell/cancel; require assigned static IP (BR-G01).

**How to test**

1. Brokers — list enabled adapters; open detail / whitelist if needed.
2. Sessions — Ensure / Refresh; Valid KPI filter.
3. Broker Health — Probe now; Healthy filter.
4. Rate Limits — Reload; OK vs Pressure filters.
5. Smart Routing — save weights; Preview candidates.
6. Orders — set Client ID (subscription client UUID), symbol, qty; Buy. History KPIs filter by status.

Copy client UUID from **Clients** (not the same as `client_order_id`, which is only an idempotency key).

---

## Static IPs and instances

**Use cases:** Provision compute attach-targets; allocate documentation-range IPs; assign to broker; attach; rotate/release with reuse policy.

**Ops flow**

1. **Instances** → Provision (mock `database` or `docker`).
2. **Static IPs** → Allocate → Assign → Attach.
3. Optional Rotate / Release / Reuse-test.

**How to test**

- Instances KPIs: Running / Suspended / Destroyed filters; Suspend / Start / Destroy actions.
- Static IPs KPIs: Available / Attached / Released filter the pool.
- Local only: activate `mock_backend=docker` and confirm containers (`brokerbridge.mock=1`).

---

## Events and ops tooling

**Use cases:** Outbox → bus; live Event Bus; replay stuck orders; inject faults that affect mock broker/infra behavior.

**How to test**

1. After an order, open Event Bus (Drain if needed); Sent / Consumed / Error filters.
2. Replay — run recovery; cards summarize CREATED / SUBMITTING / INDOUBT.
3. Chaos — enable a fault; confirm Orders / Health / IP allocate behave badly; clear; Audit shows toggles.
4. Local: `docker compose stop redis` for Dashboard redis fail.

---

## Subscriptions and security

**Use cases:** ACTIVE covering window for trading; Expire blocks trading (BR-G07); create subscription restores coverage; JWT admin/ops roles; Runtime Config secrets masked.

**How to test**

1. Clients — Create subscription → Active KPI; Expire → orders return `SUBSCRIPTION_EXPIRED`; Create again → Buy works.
2. Runtime Config — Event / Infra / Broker validate & activate; fake Vultr key fails cleanly; secrets stay `***`.
3. Sign out clears JWT.

---

## Stub pages

Security & Keys, Monitoring APIs, and Settings remain hidden stubs when not wired. Monitoring KPIs live on **Dashboard**; API exploration via **Swagger**.
