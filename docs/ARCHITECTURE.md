# Architecture

BrokerBridge is a **modular monolith**: one FastAPI process (API + Admin + OpenAPI) and one worker process, sharing Postgres, Redis, and an event bus. Integrations are behind **provider interfaces** so domain/services never import Vultr, Redis clients, Kafka clients, or broker SDKs directly.

## System overview

```mermaid
flowchart LR
  subgraph clients [Operators]
    Admin[Admin_HTML]
    Swagger[Swagger_docs]
  end
  subgraph monolith [Modular_monolith]
    API[FastAPI_api]
    Worker[Worker_outbox_consumer]
  end
  PG[(Postgres)]
  Redis[(Redis)]
  Bus[Redpanda_or_Memory]
  Admin --> API
  Swagger --> API
  API --> PG
  API --> Redis
  API --> Bus
  Worker --> PG
  Worker --> Bus
  API -.->|InfrastructureProvider| Infra[Mock_or_Vultr]
  API -.->|BrokerProvider| Broker[Mock_broker]
```

| Component | Responsibility |
|---|---|
| API | REST `/api/v1`, JWT auth, Admin static, Swagger |
| Worker | Outbox publish, event consume, background ops |
| Postgres | Brokers, IPs, instances, orders, subscriptions, config, outbox |
| Redis | Distributed locks, session cache, rate-limit windows |
| Event bus | Order/IP/config events for Admin Event Bus and ops |

## Provider architecture

Cold-start defaults come from env; **active rows in `provider_configs`** (Admin Runtime Config) win without restart.

| Kind | Local Lab typical | Render typical |
|---|---|---|
| Infrastructure | `mock` + `database` or `docker` | `mock` + **`database` only** |
| Broker | `mock` | `mock` |
| Event | `redpanda_local` (Compose) | cloud SASL or **memory** if bus unreachable |
| Lock / session / rate limit | `redis` | `redis` (e.g. Upstash) |

- **Mock infra `database`:** instances/IPs simulated in Postgres (CI, Render, default cold start).
- **Mock infra `docker`:** real containers labeled for Local Lab realism; requires Docker socket.
- **Vultr:** real adapter; activate with API key via Admin (write-only / masked secrets).

## Data model (core)

```mermaid
erDiagram
  Client ||--o{ Subscription : has
  Client ||--o{ User : may_own
  BrokerAccount ||--o{ BrokerSession : has
  BrokerAccount ||--o{ IpAssignment : assigned
  StaticIp ||--o{ IpAssignment : maps
  Instance ||--o{ IpAssignment : attaches
  BrokerAccount ||--o{ Order : routes
  Client ||--o{ Order : places
  Order ||--o{ OrderAttempt : tries
  ProviderConfig ||--|| ProviderKind : kinds
  OutboxEvent }o--|| Order : may_emit
```

Primary tables (see `app/models/`): `users`, `clients`, `subscriptions`, `broker_accounts`, `broker_sessions`, `instances`, `static_ips`, `ip_assignments`, `orders`, `order_attempts`, `outbox_events`, `provider_configs`, `configuration_items`, health/whitelist/mock_infra helpers.

## Key sequences

### Order with assigned static IP (BR-G01)

```mermaid
sequenceDiagram
  participant Admin
  participant API
  participant DB
  participant Broker as BrokerProvider
  Admin->>API: POST orders buy
  API->>DB: covering subscription?
  API->>DB: broker assigned static IP?
  API->>Broker: submit via egress context
  API->>DB: persist order plus outbox
  Note over API: Worker drains outbox to event bus
```

### IP rotate

```mermaid
sequenceDiagram
  participant Admin
  participant API
  participant Lock as Redis_lock
  participant Infra as InfraProvider
  Admin->>API: rotate static IP
  API->>Lock: acquire
  API->>Infra: allocate or attach new IP
  API->>API: drain or abort per policy
  API->>API: cutover assignment
  API->>Lock: release
```

### Runtime Config activate

Validate (probe) → write `provider_configs` → ProviderManager refresh → subsequent calls use the new adapter (no redeploy).

### Subscription expiry (BR-G07)

Expire → client suspend / infra teardown per policy → trading blocked until a **covering ACTIVE** subscription exists again (create subscription restores trading).

## HA / scale (Part 24)

Designed path (not a fixed CI RPS claim):

- **API:** horizontally scale uvicorn workers / replicas behind a load balancer (JWT + shared Postgres/Redis).
- **Worker:** partition outbox / consumer groups; isolate noisy brokers with queues if needed.
- **Redis:** locks and rate windows; fail closed with `REDIS_UNAVAILABLE` when down.
- **Events:** Redpanda/Kafka partitions by topic keys; memory provider for demos when bus is unavailable.
- **DB:** append-friendly orders/outbox; avoid hot single-row contention on rotate via locks.

Local Lab can show honest light load (`hey` / Locust against Buy) and Redis-stop chaos. Path to higher throughput is more API replicas, partitioned workers, and a healthy Kafka-compatible cluster — not a single-box Compose claim.

See also [DEMO.md](DEMO.md) for how to exercise the system and [deploy/RENDER.md](deploy/RENDER.md) for cloud constraints.
