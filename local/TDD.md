# Technical Design Document (TDD)
# BrokerBridge — Broker Network Gateway & Static IP Orchestrator

| Field | Value |
|---|---|
| Product Name | BrokerBridge |
| Document Type | Technical Design Document |
| Version | 2.3 |
| Status | Implementation-Ready |
| Companion | `PRD.md` v2.3 |
| Language/Runtime | Python 3.12 |
| Primary Framework | FastAPI (async) |

---

## Table of Contents

1. [Purpose & Scope](#1-purpose--scope)
2. [Architecture Principles](#2-architecture-principles)
3. [System Architecture](#3-system-architecture)
4. [Provider Architecture](#4-provider-architecture)
5. [Runtime Configuration & Hot Reload](#5-runtime-configuration--hot-reload)
6. [Technology Stack](#6-technology-stack)
7. [Repository & Folder Structure](#7-repository--folder-structure)
8. [Module Responsibilities](#8-module-responsibilities)
9. [Design Patterns](#9-design-patterns)
10. [Dependency Injection & App Lifecycle](#10-dependency-injection--app-lifecycle)
11. [Database Design](#11-database-design)
12. [ERD](#12-erd)
13. [API Specifications](#13-api-specifications)
14. [Event Specifications](#14-event-specifications)
15. [Routing, Health & Scoring Algorithms](#15-routing-health--scoring-algorithms)
16. [Order Engine & Idempotency](#16-order-engine--idempotency)
17. [IP Orchestration & Locking](#17-ip-orchestration--locking)
18. [Session & Rate Limit Design](#18-session--rate-limit-design)
19. [Failover & Replay](#19-failover--replay)
20. [Security Design](#20-security-design)
21. [Observability](#21-observability)
22. [Failure Simulation](#22-failure-simulation)
23. [Workers & Background Jobs](#23-workers--background-jobs)
24. [Docker & Local Development Lab](#24-docker--local-development-lab)
25. [Production Deployment (Render)](#25-production-deployment-render)
26. [Environment Variables](#26-environment-variables)
27. [Testing Strategy](#27-testing-strategy)
28. [Performance & Scalability (Part 24)](#28-performance--scalability-part-24)
29. [HA / DR](#29-ha--dr)
30. [Implementation Roadmap](#30-implementation-roadmap)
31. [Sequence Diagrams](#31-sequence-diagrams)
32. [Operations Admin UI & Swagger](#32-operations-admin-ui--swagger)
33. [Open Questions & Defaults](#33-open-questions--defaults)
34. [Appendix — Interface Skeletons](#appendix--interface-skeletons)

---

## 1. Purpose & Scope

This TDD defines **how** BrokerBridge will be built to satisfy `PRD.md` and the Senior Python assignment. It is the engineering contract for:

- Clean / layered / provider-based modular monolith
- Async FastAPI services + workers
- PostgreSQL persistence, Redis cache/lock/session, Redpanda events
- Mock and real adapters for brokers and Vultr
- **FastAPI-hosted Operations Admin HTML** (`/admin`) for module demos
- **Swagger / OpenAPI** (`/docs`, `/redoc`, `/openapi.json`) for API testing
- **Local Development Lab** — `docker compose up` with mock providers for full offline E2E demos (PRD §16)
- Deployment via Docker Compose (dev lab) and Render (prod)

Out of scope for this document: trading strategies, client trading UI / mobile, separate Next.js SPA (v1), exchange matching, extra infra beyond the Compose stack (unless later justified).

---

## 2. Architecture Principles

| Principle | Implication |
|---|---|
| Provider-Based | Domain depends on interfaces only |
| Configuration-Driven | Provider selection and policies via env + DB config |
| Runtime Reloadable | Routing weights, toggles, limits reload without process restart |
| Async-First | `asyncio` end-to-end; blocking SDKs isolated in threadpools if unavoidable |
| Event-Driven | Domain events for audit, metrics fans, async reactions |
| Stateless API | No sticky in-process state required for correctness |
| Separation of Concerns | API / Application services / Domain / Providers / Infrastructure |
| SOLID | Especially DIP for providers; SRP per module |
| Secure by Default | Encrypted secrets, RBAC, audit |
| Testability | Memory providers for unit tests; compose stack for integration |
| Local-First Lab | `docker compose up` demos all features with mocks; real providers optional via config |

---

## 3. System Architecture

### 3.1 Logical Layers

```text
┌──────────────────────────────────────────────────────────┐
│ API Layer (FastAPI routers, middleware, OpenAPI)         │
├──────────────────────────────────────────────────────────┤
│ Application Services (use-cases / orchestration)         │
├──────────────────────────────────────────────────────────┤
│ Domain (entities, rules, state machines, scoring)        │
├──────────────────────────────────────────────────────────┤
│ Ports (Provider interfaces, Repository interfaces)       │
├──────────────────────────────────────────────────────────┤
│ Adapters (Providers, SQLAlchemy repos, HTTP clients)     │
├──────────────────────────────────────────────────────────┤
│ Infrastructure (Postgres, Redis, Redpanda, Vultr, Brokers)│
└──────────────────────────────────────────────────────────┘
```

### 3.2 Runtime Components

| Component | Role |
|---|---|
| `api` | Stateless HTTP API |
| `worker` | Order consumers, health probes, whitelist sync, replay, expiry |
| `postgres` | System of record |
| `redis` | Cache, distributed locks, sessions, rate buckets |
| `redpanda` | Event bus (Kafka API) |

Optional: separate worker processes by queue topic for scale.

### 3.3 Request Path (Order Submit)

```text
Client
  → Middleware (request_id, auth, HMAC, rate limit edge)
  → Orders API
  → OrderService.place()
      → SubscriptionGuard
      → IdempotencyStore
      → RoutingEngine.select()
      → SessionService.ensure()
      → IpAssignmentService.ensure()
      → OrderSubmissionService.submit()  # BrokerProvider + bound egress IP
      → OrderRepository.save()
      → EventPublisher.publish()
      → AuditLogger.record()
  → Response DTO
```

### 3.4 Architecture Style Choice

**Modular monolith** (single deployable, multiple modules) — not microservices.

Rationale: assignment needs cohesion, shared transactions for IP/order mapping, simpler ops for Render, while still allowing later extraction of workers/providers.

---

## 4. Provider Architecture

### 4.1 Provider Manager

`ProviderManager` loads **runtime** provider configuration (DB) with bootstrap env as fallback defaults, and constructs/caches provider instances keyed by `(kind, scope, version)`.

```text
ProviderManager
  ├── get_broker_provider(type, credentials?) → BrokerProvider
  ├── get_infrastructure_provider(scope=global|client_id) → InfrastructureProvider
  ├── get_event_provider() → EventProvider
  ├── get_cache_provider() → CacheProvider
  ├── get_lock_provider() → LockProvider
  ├── get_session_provider() → SessionProvider
  ├── invalidate(kind, scope?)           # after config change
  └── rebuild(kind, scope?)              # eager rebuild + optional health probe
```

Business services receive ports via DI—never construct Redis/Kafka/Vultr clients inline.

**Resolution order for infrastructure (example):**
1. Active `provider_configs` row for `(kind=infrastructure, client_id=X)` if present  
2. Else active global `provider_configs` for infrastructure  
3. Else bootstrap env `INFRA_PROVIDER` / optional legacy `VULTR_API_KEY`  
4. Else safe default `mock`

On config activation, Manager **must not** require process restart: decrypt secrets → factory.create → swap cache → emit `provider.activated`.

### 4.2 BrokerProvider

```text
BrokerProvider (Protocol)
├── MockBrokerProvider
├── RealBrokerProvider          # generic HTTP adapter template
├── ZerodhaProvider             # optional sample
├── AngelOneProvider            # optional sample
└── IBKRProvider                # optional sample
```

**Responsibilities**
- authenticate / refresh session (or delegate token ops)
- place/cancel/status/history
- fetch capabilities
- fetch whitelist (JSON/XML raw)
- health probe
- support fault-injection hooks when enabled

**Egress binding**  
Submission must execute in a context where HTTP client uses the assigned static IP (or simulated binding in mock). Design: `BrokerRequestContext(ip=..., session=...)`.

### 4.3 InfrastructureProvider

```text
InfrastructureProvider
├── MockInfrastructureProvider
└── VultrProvider
```

Methods (minimum):
- `create_instance`, `destroy_instance`, `suspend_instance`
- `create_ip`, `delete_ip`, `attach_ip`, `detach_ip`
- `set_auto_renew(resource_id, enabled: bool)`
- `list_ips(region)`, `get_ip(id)`

### 4.4 EventProvider

```text
EventProvider
├── MemoryEventProvider      # asyncio pub/sub for tests/dev
└── RedpandaProvider         # Kafka producer/consumer
```

### 4.5 CacheProvider / LockProvider / SessionProvider

| Port | Memory | Redis |
|---|---|---|
| CacheProvider | MemoryCache | RedisCache |
| LockProvider | MemoryLock | RedisLock (token + TTL) |
| SessionProvider | MemorySession | RedisSession |

### 4.6 Adding a New Broker Without Routing Changes

1. Implement `BrokerProvider` adapter.
2. Register in provider registry: `{"angelone": AngelOneProvider}`.
3. Insert `broker_accounts` row with `provider_type=angelone` + encrypted credentials + capabilities.
4. Routing discovers it via DB/metadata—**no change** to RoutingEngine code.

---

## 5. Runtime Configuration & Hot Reload

### 5.0 Design Goal (PRD §14 / FR-21)

Ship with **mock** integrations. Allow any admin/tester to attach **real** Vultr (and broker) credentials through Admin APIs so the running system uses real services **without editing `.env` and without restarting** the API/worker processes.

### 5.1 Configuration Sources (priority high→low)

| Priority | Source | Role |
|---|---|---|
| 1 | Active DB `provider_configs` (scoped) | Integration provider type + encrypted secrets |
| 2 | DB `configuration_items` | Policies: routing, limits, rotation, faults |
| 3 | Environment variables | **Bootstrap only** + optional legacy fallback |
| 4 | Code defaults | `mock` providers, conservative policies |

### 5.2 Bootstrap vs Runtime Split

**Bootstrap (env — restart to change):**
- `DATABASE_URL`, `REDIS_URL`, `REDPANDA_BROKERS`
- `SECRETS_FERNET_KEY` / KMS reference (encrypts runtime secrets)
- `JWT_SECRET` (or asymmetric key material)
- `APP_ENV`, `LOG_LEVEL`

**Runtime (DB / Admin API — no restart):**
- Infrastructure provider `mock|vultr` + Vultr `api_key`, `default_region`
- Broker account credentials / enablement (also `broker_accounts`)
- Default broker provider hints
- Routing weights, health thresholds, rate limits
- IP reuse / rotation / teardown policies
- Fault injection flags
- Optional logical switches for Event/Cache/Lock/Session **implementations** in dev (changing Redis/Redpanda **connection URLs** remains bootstrap)

### 5.3 `provider_configs` Model

```text
provider_configs
  id UUID PK
  kind            # infrastructure | broker_default | event | cache | lock | session
  provider_type   # mock | vultr | redpanda | redis | memory | zerodha | ...
  scope_type      # global | client
  client_id       # nullable; set when scope_type=client
  status          # pending | active | retired | failed_validation
  version         # monotonic per (kind, scope)
  config_encrypted TEXT/BYTEA   # JSON secrets+options encrypted
  config_non_secret JSONB       # region, timeouts, flags (safe to return)
  last_validation_status
  last_validation_at
  activated_at
  created_by
  created_at
```

Constraints:
- At most **one** `active` row per `(kind, scope_type, client_id)`
- Keep prior versions as `retired` for rollback (retain last N)

### 5.4 Dynamic Policy Keys (`configuration_items`)

| Key | Purpose |
|---|---|
| `routing.weights.*` | Health/latency/success weights |
| `routing.policy` | WEIGHTED_SCORE / … |
| `routing.unhealthy_threshold` | Score cutoff |
| `rate_limit.{broker}.rps` | Quotas |
| `ip.reuse.cooldown_hours` | Reuse policy |
| `ip.rotation.drain_timeout_seconds` | Drain |
| `ip.rotation.on_timeout` | ABORT / FORCE |
| `subscription.teardown_mode` | SUSPEND / DESTROY |
| `fault_injection.*` | Simulation flags |
| `providers.hot_swap.enabled` | Feature flag |

### 5.5 Validate → Stage → Activate → Reload

```text
Admin PUT /admin/providers/{kind}
  → validate schema (Pydantic)
  → if validate_first: factory.build_ephemeral(type, secrets).probe()
  → on failure: status=failed_validation; leave active unchanged; return 422
  → encrypt secrets; insert version N+1 status=pending
  → mark N+1 active; retire previous
  → ProviderManager.invalidate/rebuild
  → publish config.updated + provider.activated
  → audit (redacted)
```

**Probe examples**
- Vultr: lightweight authenticated GET (account/regions)
- Broker: auth or capabilities call
- Mock: always succeeds

**In-flight safety:** long-running operations hold a reference to the provider instance obtained at start; new requests see the new instance after swap.

### 5.6 Multi-Instance Reload

- Write DB (source of truth)
- Publish `config.updated` / `provider.activated` on Redpanda topic `brokerbridge.config` (and/or Redis pubsub)
- Each API/worker refreshes ConfigService snapshot and ProviderManager cache
- Fallback: poll `provider_configs.version` every N seconds if bus unavailable

### 5.7 Legacy Env Fallback (optional)

For local convenience only:

```text
INFRA_PROVIDER=vultr
VULTR_API_KEY=...
```

Resolution still prefers **active DB `provider_configs`**. Document clearly: runtime Admin config wins. Production demos should use Admin API, not env keys.

### 5.8 Guarantees & Non-Guarantees

| Change | No restart? |
|---|---|
| mock ↔ vultr + API key via Admin API | **Yes** |
| Broker credentials / enable flags | **Yes** |
| Routing/rate/IP policies | **Yes** |
| `DATABASE_URL` / `REDIS_URL` / Fernet key | **No** (bootstrap) |
| Switching Event bus **connection** string | **No** (rolling restart) |
| memory ↔ redis **implementation** when Redis URL already bootstrapped | **Yes** (rebuild client from existing URL) |

---

## 6. Technology Stack

| Area | Choice |
|---|---|
| Language | Python 3.12 |
| API | FastAPI + Uvicorn |
| Validation | Pydantic v2 |
| ORM | SQLAlchemy 2.x (async) |
| Migrations | Alembic |
| DB | PostgreSQL 16 |
| Cache/Lock/Session | Redis 7 |
| Events | Redpanda (Kafka compatible) |
| Auth | JWT (python-jose/PyJWT), API keys, HMAC |
| Crypto | cryptography (Fernet) KMS-ready wrapper |
| Metrics | prometheus_client |
| Logging | structlog JSON |
| HTTP client | httpx (async) |
| Testing | pytest, pytest-asyncio, httpx ASGI |
| Containers | Docker, Docker Compose |
| Prod host | Render |

---

## 7. Repository & Folder Structure

```text
BrokerBridge/
├── app/
│   ├── main.py                 # FastAPI app: API + /docs + mount /admin
│   ├── api/
│   │   ├── deps.py
│   │   ├── router.py
│   │   ├── routes/
│   │   │   ├── auth.py
│   │   │   ├── orders.py
│   │   │   ├── brokers.py
│   │   │   ├── infrastructure.py
│   │   │   ├── monitoring.py
│   │   │   ├── admin.py
│   │   │   └── health.py
│   │   └── middleware/
│   ├── auth/
│   ├── broker/
│   ├── routing/
│   ├── orders/
│   ├── ip_manager/
│   ├── infrastructure/
│   ├── sessions/
│   ├── health/
│   ├── events/
│   ├── monitoring/
│   ├── rate_limit/
│   ├── replay/
│   ├── failure_sim/
│   ├── repositories/
│   ├── services/
│   ├── workers/
│   ├── models/          # SQLAlchemy models
│   ├── schemas/         # Pydantic schemas (drive OpenAPI/Swagger)
│   ├── providers/
│   │   ├── base.py
│   │   ├── manager.py
│   │   ├── broker/
│   │   ├── infrastructure/
│   │   ├── events/
│   │   ├── cache/
│   │   ├── locks/
│   │   └── sessions/
│   ├── core/
│   │   ├── logging.py
│   │   ├── metrics.py
│   │   ├── security.py
│   │   └── exceptions.py
│   ├── config/
│   ├── shared/
│   └── static/
│       └── admin/                 # Operations Admin HTML (from sample UX)
│           ├── index.html
│           ├── css/               # optional extracted styles
│           └── js/
│               ├── api.js         # fetch wrapper + JWT storage
│               ├── auth.js
│               └── pages/         # per-page loaders wired to /api/v1
├── migrations/
├── tests/
├── docs/                # diagrams exports optional
├── local/               # PRD, TDD, assignment PDFs, HTML prototype reference
│   └── brokerbridge_operations_platform.html   # UX baseline / prototype
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml / requirements.txt
└── README.md
```

---

## 8. Module Responsibilities

| Module | Responsibility |
|---|---|
| `api` | HTTP boundaries, DTO validation, status codes |
| `auth` | JWT/API key/HMAC/RBAC |
| `broker` | Broker account domain + capability models |
| `routing` | Candidate filtering, scoring, failover chain |
| `orders` | Order state machine, submission orchestration |
| `ip_manager` | Assignment, rotation, reuse policy, whitelist sync orchestration |
| `infrastructure` | Instance/IP lifecycle use-cases over InfraProvider |
| `sessions` | Token lifecycle |
| `health` | Probes + scoring |
| `rate_limit` | Quotas + queue/reroute decisions |
| `events` | Publish helpers + consumer wiring |
| `monitoring` | Read models for dashboard APIs |
| `failure_sim` | Fault injection controls |
| `replay` | Startup recovery scanner |
| `repositories` | Persistence adapters |
| `services` | Cross-module application services (optional façade) |
| `workers` | Background loops / queue consumers |
| `providers` | All external adapters |
| `config` | Settings + dynamic config service |
| `core` | Cross-cutting primitives |
| `static/admin` | Operations Admin HTML+JS (demo UI; calls `/api/v1`) |

---

## 9. Design Patterns

| Pattern | Where |
|---|---|
| Adapter | Broker/Infra/Event/Cache/Lock/Session providers |
| Strategy | Routing policies, teardown modes, rotation timeout policies |
| Repository | SQLAlchemy repositories |
| Factory | ProviderManager |
| Service Layer | OrderService, IpRotationService, … |
| Observer | Event publish/subscribe |
| Dependency Injection | FastAPI `Depends` + app state |
| Outbox (recommended) | Transactional outbox for reliable events |
| Single-flight | Session refresh coalescing |
| Circuit breaker (optional) | Per-broker temporary open state |

---

## 10. Dependency Injection & App Lifecycle

### Startup

1. Load env settings.
2. Init DB engine/session factory.
3. Init Redis (if configured).
4. Init EventProvider.
5. Build ProviderManager.
6. Load dynamic config snapshot.
7. Start metrics.
8. (API only) mount routes.
9. (Worker only) start consumers + schedulers.

### Shutdown

Graceful: stop consumers, flush producers, dispose engine.

### DI Style

```python
# Conceptual
async def get_order_service(request: Request) -> OrderService:
    return request.app.state.container.order_service
```

Use a simple `Container` object rather than a heavy DI framework unless needed.

---

## 11. Database Design

### 11.1 Tables (Logical Schema)

#### `clients`
- `id` UUID PK  
- `name`  
- `status` (`active|suspended`)  
- `created_at`

#### `users` (API principals)
- `id` UUID PK  
- `client_id` FK nullable (platform admins null)  
- `email` unique  
- `role` (`client|admin|ops|readonly`)  
- `password_hash` nullable  
- `api_key_hash` nullable  
- `api_key_prefix`  
- `hmac_secret_encrypted` nullable  
- `is_active`  
- `created_at`

#### `subscriptions`
- `id` UUID PK  
- `client_id` FK  
- `status` (`active|expired|cancelled`)  
- `starts_at`, `ends_at`  
- `teardown_mode`  
- `teardown_completed_at` nullable

#### `broker_accounts`
- `id` UUID PK  
- `client_id` FK  
- `provider_type`  
- `display_name`  
- `priority` int  
- `enabled` bool  
- `allowed_regions` JSONB  
- `capabilities` JSONB  
- `credentials_encrypted` BYTEA/TEXT  
- `rate_limit_rps` numeric  
- `created_at`, `updated_at`

#### `broker_sessions`
- `id` UUID PK  
- `broker_account_id` FK unique  
- `access_token_encrypted`  
- `refresh_token_encrypted`  
- `expires_at`  
- `status`  
- `updated_at`

#### `instances`
- `id` UUID PK  
- `client_id` FK  
- `provider` (`vultr|mock`)  
- `external_id`  
- `region`  
- `status`  
- `auto_renew` bool  
- `metadata` JSONB

#### `static_ips`
- `id` UUID PK  
- `provider`  
- `external_id`  
- `ip_address` inet/text unique  
- `region`  
- `status` (`available|allocated|attached|draining|detached|released|quarantined`)  
- `instance_id` FK nullable  
- `health_score`  
- `metadata` JSONB

#### `ip_assignments`
- `id` UUID PK  
- `client_id` FK  
- `broker_account_id` FK  
- `static_ip_id` FK  
- `status` (`active|draining|released`)  
- `assigned_at`, `released_at`  
- Unique partial index: one `active` assignment per broker_account  
- Unique constraint supporting BR-G04 via `broker_ip_usage_history`

#### `broker_ip_usage_history`
- `id` UUID PK  
- `broker_account_id` FK  
- `static_ip_id` FK  
- `used_at`, `released_at`  
- `reuse_eligible_at`  
- Used to enforce “cannot reassign same IP to same broker until policy allows”

#### `whitelist_snapshots`
- `id` UUID PK  
- `broker_account_id` FK  
- `raw_format` (`json|xml`)  
- `raw_payload` TEXT  
- `normalized` JSONB  
- `fetched_at`

#### `whitelist_findings`
- `id` UUID PK  
- `broker_account_id` FK  
- `ip_address`  
- `finding_type` (`missing|duplicate|stale|unauthorized|ok`)  
- `details` JSONB  
- `detected_at`, `resolved_at`

#### `orders`
- `id` UUID PK  
- `client_id` FK  
- `client_order_id` TEXT  
- Unique(`client_id`,`client_order_id`)  
- `side` (`BUY|SELL`)  
- `symbol`, `quantity`, `order_type`, `time_in_force`  
- `status`  
- `broker_account_id` FK nullable  
- `static_ip_id` FK nullable  
- `preferred_broker_id` nullable  
- `region_preference` nullable  
- `error_code` nullable  
- `created_at`, `updated_at`

#### `order_attempts`
- `id` UUID PK  
- `order_id` FK  
- `attempt_no` int  
- `broker_account_id` FK  
- `static_ip_id` FK  
- `status` (`submitting|submitted|failed|indoubt|reconciled`)  
- `broker_order_id` nullable  
- `request_payload` JSONB  
- `response_payload` JSONB  
- `error` TEXT  
- `idempotency_key`  
- `created_at`, `updated_at`

#### `health_snapshots`
- `id` BIGSERIAL  
- `broker_account_id` FK  
- `latency_ms`, `success_rate`, `timeout_rate`, `connectivity`  
- `ip_health`  
- `score`  
- `status` (`healthy|degraded|unhealthy`)  
- `measured_at`

#### `rate_limit_events` (optional durable)
- `id`, `broker_account_id`, `client_id`, `hits`, `window_start`

#### `audit_logs`
- `id` BIGSERIAL  
- `actor_user_id` nullable  
- `actor_type`  
- `action`  
- `entity_type`, `entity_id`  
- `request_id`  
- `before` JSONB, `after` JSONB  
- `created_at`  
- **No updates/deletes** via app

#### `provider_configs`
- `id` UUID PK  
- `kind` (`infrastructure|broker_default|event|cache|lock|session`)  
- `provider_type` TEXT  
- `scope_type` (`global|client`)  
- `client_id` UUID FK nullable  
- `status` (`pending|active|retired|failed_validation`)  
- `version` INT  
- `config_encrypted` TEXT/BYTEA  
- `config_non_secret` JSONB  
- `last_validation_status` TEXT nullable  
- `last_validation_at` TIMESTAMPTZ nullable  
- `activated_at` TIMESTAMPTZ nullable  
- `created_by` UUID nullable  
- `created_at` TIMESTAMPTZ  
- Unique partial index: one `active` per `(kind, scope_type, coalesce(client_id, zero-uuid))`  
- Index `(kind, scope_type, client_id, version DESC)`

#### `configuration_items`
- `id` UUID PK  
- `key` unique  
- `value` JSONB  
- `version` int  
- `updated_by`  
- `updated_at`

#### `outbox_events` (recommended)
- `id` UUID PK  
- `event_type`  
- `payload` JSONB  
- `status` (`pending|sent|error`)  
- `created_at`, `sent_at`

### 11.2 Indexing Notes

- `orders(client_id, created_at DESC)`
- `orders(status)` for replay scanner
- `order_attempts(status)` 
- `static_ips(region, status)`
- `ip_assignments(broker_account_id)` where status=active
- `health_snapshots(broker_account_id, measured_at DESC)`
- `audit_logs(entity_type, entity_id, created_at)`
- `provider_configs(kind, scope_type, client_id, status)`

### 11.3 Transaction Boundaries

- Creating order + first attempt + outbox row: **one DB transaction**
- IP assignment mutation + usage history + audit + outbox: **one DB transaction**
- Provider activate: retire old + insert/activate new + audit + outbox: **one DB transaction**; ProviderManager rebuild **after** commit
- Broker HTTP call: **outside** DB transaction; update attempt after response

---

## 12. ERD

```text
clients 1──* broker_accounts
clients 1──* subscriptions
clients 1──* orders
clients 1──* instances

broker_accounts 1──1 broker_sessions
broker_accounts 1──* ip_assignments
broker_accounts 1──* order_attempts
broker_accounts 1──* health_snapshots
broker_accounts 1──* whitelist_findings
broker_accounts 1──* broker_ip_usage_history

static_ips 1──* ip_assignments
static_ips 1──* order_attempts
static_ips *──1 instances (optional)

orders 1──* order_attempts
orders *──1 static_ips (assigned at submit)
orders *──1 broker_accounts (selected)

users *──1 clients (nullable)
clients 1──* provider_configs (optional per-client overrides)
provider_configs (global rows have null client_id)
```

---

## 13. API Specifications

Base: `/api/v1`  
Auth: `Authorization: Bearer <JWT>` or `X-API-Key`  
Optional: `X-Signature`, `X-Timestamp` for HMAC  
Idempotency: `client_order_id` in body (orders)

### 13.0 OpenAPI / Swagger (required)

FastAPI built-in documentation **must be enabled** for local and assignment demos:

| URL | Purpose |
|---|---|
| `/docs` | Swagger UI — try-it-out for all tagged routes |
| `/redoc` | ReDoc — readable reference |
| `/openapi.json` | OpenAPI 3 schema |

App factory guidelines:
```python
FastAPI(
    title="BrokerBridge API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)
```

- Every router uses OpenAPI `tags` (`auth`, `orders`, `brokers`, `infrastructure`, `monitoring`, `admin`, `health`).
- Pydantic request/response models drive accurate Swagger schemas.
- Admin UI header includes link **API Docs → `/docs`**.
- Assignment default: docs open (no auth wall). Optional later: gate `/docs` behind admin in hardened prod via settings flag `DOCS_ENABLED` / `DOCS_REQUIRE_AUTH`.

### 13.1 Auth

| Method | Path | Description |
|---|---|---|
| POST | `/auth/token` | Login → JWT |
| POST | `/auth/api-keys` | Admin create API key |
| POST | `/auth/rotate-secrets` | Secret rotation |

### 13.2 Orders

| Method | Path | Description |
|---|---|---|
| POST | `/orders/buy` | Place buy |
| POST | `/orders/sell` | Place sell |
| POST | `/orders/{id}/cancel` | Cancel |
| GET | `/orders/{id}` | Status |
| GET | `/orders` | History (filters, pagination) |

**POST /orders/buy request**
```json
{
  "client_order_id": "c-10001",
  "symbol": "AAPL",
  "quantity": 10,
  "order_type": "MARKET",
  "time_in_force": "DAY",
  "preferred_broker_id": null,
  "region_preference": "ewr"
}
```

**Responses**
- `201` created/submitted
- `200` idempotent replay of existing
- `402/403` subscription expired / forbidden
- `409` conflict
- `422` validation
- `503` queue full / dependency unavailable

### 13.3 Brokers

| Method | Path | Description |
|---|---|---|
| POST | `/brokers` | Onboard broker account |
| GET | `/brokers` | List |
| GET | `/brokers/{id}` | Detail + capabilities |
| PATCH | `/brokers/{id}` | Enable/disable, priority, limits |
| POST | `/brokers/{id}/capabilities/refresh` | Discovery refresh |
| GET | `/brokers/{id}/sessions` | Session status |

### 13.4 Infrastructure & IPs

| Method | Path | Description |
|---|---|---|
| POST | `/infrastructure/instances` | Provision |
| DELETE | `/infrastructure/instances/{id}` | Destroy |
| POST | `/infrastructure/ips` | Allocate |
| POST | `/infrastructure/ips/{id}/attach` | Attach |
| POST | `/infrastructure/ips/{id}/detach` | Detach |
| DELETE | `/infrastructure/ips/{id}` | Release |
| POST | `/infrastructure/brokers/{broker_id}/rotate-ip` | Zero-downtime rotate |
| GET | `/infrastructure/assignments` | Client/broker/IP map |
| POST | `/infrastructure/brokers/{broker_id}/whitelist/sync` | Sync now |

### 13.5 Monitoring

| Method | Path | Description |
|---|---|---|
| GET | `/monitoring/brokers/health` | Health scores |
| GET | `/monitoring/sessions` | Session statuses |
| GET | `/monitoring/ips` | IP health/pools |
| GET | `/monitoring/failovers` | Recent failovers |
| GET | `/monitoring/rate-limits` | Quotas |
| GET | `/monitoring/orders/engine` | Queue depth, throughput |

### 13.6 Admin / Config / Simulation / Providers

| Method | Path | Description |
|---|---|---|
| GET/PUT | `/admin/config/{key}` | Dynamic policy config |
| GET | `/admin/providers` | List active providers (secrets masked) |
| GET | `/admin/providers/{kind}` | Get active config for kind (masked) |
| PUT | `/admin/providers/{kind}` | Stage/activate provider (hot-swap) |
| POST | `/admin/providers/{kind}/test` | Validate credentials without activating |
| POST | `/admin/providers/{kind}/rollback` | Restore previous active version |
| GET | `/admin/providers/{kind}/history` | Version history (masked) |
| POST | `/admin/failure-sim/{profile}` | Enable injection |
| DELETE | `/admin/failure-sim/{profile}` | Clear |
| POST | `/admin/replay/run` | Trigger replay scan |

**PUT `/admin/providers/infrastructure` body**
```json
{
  "provider_type": "vultr",
  "scope": "global",
  "client_id": null,
  "validate_first": true,
  "activate": true,
  "config": {
    "api_key": "vultr-xxxxx",
    "default_region": "ewr"
  }
}
```

**Responses**
- `200` activated (secrets redacted in body)
- `422` `PROVIDER_VALIDATION_FAILED` — previous active unchanged
- `409` concurrent activation conflict (retry)

RBAC: `admin` for PUT/rollback; `admin` or `ops` for GET/test.

### 13.7 Health & Metrics

| Method | Path | Description |
|---|---|---|
| GET | `/health/live` | Liveness |
| GET | `/health/ready` | Readiness (db/redis) |
| GET | `/metrics` | Prometheus |

### 13.8 Error Envelope

```json
{
  "error_code": "NO_ROUTE",
  "message": "No eligible broker for capability OPTIONS",
  "request_id": "…",
  "details": {}
}
```

---

## 14. Event Specifications

### 14.1 Envelope

```json
{
  "event_id": "uuid",
  "event_type": "order.submitted",
  "occurred_at": "ISO-8601",
  "producer": "brokerbridge-api",
  "correlation_id": "request_id",
  "payload": {}
}
```

### 14.2 Topics (Redpanda)

| Topic | Events |
|---|---|
| `brokerbridge.orders` | order.* |
| `brokerbridge.brokers` | broker.down, broker.recovered, session.refreshed |
| `brokerbridge.ip` | ip.allocated, ip.rotated, ip.released, whitelist.sync.completed |
| `brokerbridge.subscriptions` | subscription.expired |
| `brokerbridge.config` | config.updated, provider.activated, provider.validation_failed |

### 14.3 Payload Examples

**ip.rotated**
```json
{
  "client_id": "…",
  "broker_account_id": "…",
  "old_ip_id": "…",
  "new_ip_id": "…",
  "old_ip": "45.76.1.10",
  "new_ip": "45.76.1.22"
}
```

**broker.down**
```json
{
  "broker_account_id": "…",
  "reason": "timeout_threshold_exceeded",
  "health_score": 12.5
}
```

---

## 15. Routing, Health & Scoring Algorithms

### 15.1 Health Score

```text
latency_score      = clamp(100 * (1 - latency_ms / latency_budget_ms), 0, 100)
success_score      = success_rate * 100
connectivity_score = 100 if up else 0
timeout_penalty    = timeout_rate * 100
ip_score           = ip_health_score

score = w_lat*latency_score + w_succ*success_score + w_conn*connectivity_score
      + w_to*(100 - timeout_penalty) + w_ip*ip_score
```

Default weights (sum≈1): `0.25, 0.30, 0.15, 0.20, 0.10`.

Statuses: `>=80 healthy`, `50–79 degraded`, `<50 unhealthy` (configurable).

### 15.2 Route Score

```text
route_score = health_score
            + priority_bonus          # e.g., priority * 2
            - rate_limit_pressure     # 0–20
            + sticky_bonus            # if preferred broker
```

Select max `route_score`; build failover chain by descending score among remaining eligibles.

---

## 16. Order Engine & Idempotency

### 16.1 Ingress Modes

- **Mode A (default):** API persists `CREATED`, enqueues job, returns quickly with status; workers submit.
- **Mode B:** API submits inline for low-latency demos with bounded timeout.

Configurable via `orders.execution_mode`.

### 16.2 Concurrency Model

- Global asyncio semaphore `MAX_INFLIGHT_ORDERS`
- Per-broker semaphore / queue partition
- Redis queue or Redpanda topic `orders.submit` for multi-instance workers
- Target demo: ~5,000 orders/min with MockBrokerProvider

### 16.3 Retries

- Retryable: timeout, 429, 502/503/504
- Non-retryable: 400 validation, insufficient funds (broker), auth hard-fail after refresh attempt
- Backoff: `min(max_backoff, base * 2**attempt) + jitter`

### 16.4 Idempotency

- Unique `(client_id, client_order_id)`
- Submission token = hash(`client_id`,`client_order_id`,`attempt_broker`) or stable key across failover if business requires single economic order—**prefer stable client_order_id end-to-end** and broker-native idempotency fields when available

---

## 17. IP Orchestration & Locking

### 17.1 Lock Keys

| Resource | Key |
|---|---|
| Broker IP mutation | `lock:broker:{broker_id}:ip` |
| Static IP allocate | `lock:ip:{ip_id}` |
| Session refresh | `lock:session:{broker_id}` |

Redis lock algorithm: set token with TTL; unlock only if token matches; extend TTL while rotation drain runs (watchdog).

### 17.2 Rotation Algorithm (Pseudo)

```text
acquire lock broker
allocate/select new_ip in region
attach new_ip
whitelist sync (best effort + gate)
mark old assignment DRAINING
wait until in_flight(old_ip)==0 or timeout
if success or FORCE:
  activate new assignment
  release old per reuse policy (write usage history)
  publish ip.rotated
else:
  abort; cleanup new_ip if unused
release lock
```

### 17.3 Reuse Policy Enforcement

Before assigning IP I to broker B:
1. Check no conflicting active assignment violating constraints.
2. Check `broker_ip_usage_history` for B+I where `reuse_eligible_at > now()` → reject.
3. Allow share of I across different brokers if statuses permit (BR-G03).

---

## 18. Session & Rate Limit Design

### 18.1 Session Service

```text
ensure_session(broker_id):
  cached = session_provider.get()
  if valid_for(skew): return cached
  with lock(broker_id):
    recheck
    tokens = broker_provider.refresh(credentials)
    persist encrypted + session_provider.set(ttl)
    publish session.refreshed
```

### 18.2 Rate Limit

Redis sliding window or token bucket:
- Key `rl:broker:{id}`
- On exceed → policy from config: `REROUTE|QUEUE|REJECT`

---

## 19. Failover & Replay

### 19.1 Failover

```text
on failure(attempt):
  if ack_received: do not failover submit; handle cancel/status
  if uncertain: mark INDOUBT; enqueue reconcile
  else: next broker in chain; new attempt row; submit once
```

### 19.2 Replay Scanner (Startup / Admin)

1. Select orders in `SUBMITTING|PENDING|INDOUBT` older than threshold.
2. For each: load attempts; query broker status if broker_order_id exists.
3. Terminalize or retry safely.
4. Dead-letter after max attempts with alert.

### 19.3 Exactly-Once Intent

Documented guarantee: **at-most-once broker submission per confirmed ack**; **at-least-once internal processing** with idempotent state transitions. True cross-broker exactly-once is not physically possible without broker support—mitigate via reconciliation.

---

## 20. Security Design

| Control | Design |
|---|---|
| JWT | HS256/RS256; short TTL; refresh optional |
| RBAC | Role checks on routes |
| API Keys | Store hash; show once on create |
| HMAC | `sign = HMAC_SHA256(secret, timestamp+method+path+body)` |
| Encryption | Fernet key from env `SECRETS_FERNET_KEY`; encrypt credentials |
| Secret rotation | Dual accept window for JWT/API/HMAC |
| Audit | Append-only |
| TLS | Terminated at Render / reverse proxy |

Roles:
- `client`: own orders/brokers read+trade
- `ops`: monitoring + failure sim (non-prod)
- `admin`: config, infra, onboard
- `readonly`: monitoring GET only

---

## 21. Observability

### Metrics (Prometheus)

- `http_requests_total`
- `order_submit_total{broker,result}`
- `order_latency_seconds{broker}`
- `broker_health_score{broker}`
- `ip_rotation_total{result}`
- `failover_total{from_broker,to_broker}`
- `queue_depth`
- `rate_limit_hits_total{broker}`
- `replay_orders_total{result}`
- `provider_activate_total{kind,type,result}`
- `provider_validation_total{kind,type,result}`

### Logging

structlog JSON: `timestamp, level, logger, request_id, client_id, broker_id, order_id, event, error_code, message`  
Never log raw provider secrets; log `provider_kind`, `provider_type`, `version` only.

### Tracing (optional stretch)

OpenTelemetry hooks; not required for assignment pass.

---

## 22. Failure Simulation

Admin enables profiles stored in dynamic config / redis flags:

| Profile | Effect |
|---|---|
| `BROKER_TIMEOUT` | Mock provider sleeps > client timeout |
| `DNS_FAIL` | Raise resolution error |
| `TLS_FAIL` | Raise TLS error |
| `IP_BLACKLIST` | Mark IP quarantined |
| `PARTIAL_OUTAGE` | Intermittent 503 |

Always publish recovery events when cleared.

---

## 23. Workers & Background Jobs

| Worker | Trigger | Work |
|---|---|---|
| OrderSubmitConsumer | queue | submit/cancel |
| HealthProbeScheduler | interval | probe + snapshot |
| WhitelistSyncScheduler | interval | sync all active brokers |
| SessionRefreshScheduler | interval | proactive refresh |
| SubscriptionExpiryScheduler | interval | enforce BR-G07 |
| ReplayScanner | startup + interval | recover |
| OutboxPublisher | interval | drain outbox → EventProvider |
| IpDrainWatcher | during rotation | track in-flight |

Packaging: same image, command `python -m app.workers.main` vs `uvicorn app.main:app`.

---

## 24. Docker & Local Development Lab

### 24.1 Goal (PRD §16)

Clone the repo and run:

```bash
docker compose up --build
```

This starts a **complete local lab** where every assignment feature is demonstrable **without** Vultr accounts or real broker credentials. Mock providers simulate external systems; platform services are real containers.

### 24.2 Compose services (assignment scope only)

| Service | Image/role |
|---|---|
| `api` | FastAPI app: `/api/v1`, `/admin`, `/docs`, `/redoc`, `/metrics` |
| `worker` | Background consumers/schedulers (same image, different command) |
| `postgres` | PostgreSQL 16 |
| `redis` | Redis 7 |
| `redpanda` | Kafka-compatible broker (+ optional console) |

**Do not** add unrelated services (Elasticsearch, MinIO, full local Kubernetes, etc.) for the assignment baseline.

### 24.3 Real vs mocked in the lab

| Real (Compose) | Mocked (providers) |
|---|---|
| API, Admin, Swagger, workers | Broker HTTP APIs |
| PostgreSQL | Vultr public IPs / instances |
| Redis locks/cache/sessions/rate limits | Real broker whitelist network calls |
| Redpanda event bus | External DNS/TLS (except via simulator) |

`MockInfrastructureProvider` allocates **documentation-range** IPs (`198.51.100.0/24`, `203.0.113.0/24`), tracks full lifecycle, assignments, reuse policy, audit, and events — same domain services as `VultrProvider`.

`MockBrokerProvider` simulates place/cancel/status, sessions, capabilities, whitelist fixtures, rate limits, and fault-injection hooks.

### 24.4 Dual execution modes

```text
Local Mode                          Real Integration Mode
─────────────────────────────       ────────────────────────────────
docker compose up                   Same application code/image
provider_configs → mock             provider_configs → vultr / real brokers
                                    (Admin hot-swap or bootstrap fallback)
shared: routing, orders, locks,     shared: identical business logic
events, health, replay, admin UI
```

**Principle:** switching local ↔ real changes **provider implementations + config only**. No changes to domain services, repositories, routing formulas, or API contracts.

Bootstrap env fallbacks for empty DB:

```text
INFRA_PROVIDER=mock
BROKER_PROVIDER=mock
CACHE_PROVIDER=redis
LOCK_PROVIDER=redis
SESSION_PROVIDER=redis
EVENT_PROVIDER=redpanda
# VULTR_API_KEY not required for local lab
```

Seed migration inserts active mock `provider_configs`. Runtime Admin can still activate Vultr later without Compose changes.

### 24.5 Local chaos / dependency outages

| Scenario | Mechanism |
|---|---|
| Redis down | `docker compose stop redis` |
| Redpanda down | `docker compose stop redpanda` (outbox retry / degrade) |
| Postgres down | `docker compose stop postgres` (API readiness fails) |
| API/worker crash | `docker compose restart api|worker` → ReplayScanner |
| Broker timeout / DNS / TLS / IP blacklist | Admin Failure Simulator profiles on mocks |
| Lock contention | Parallel rotate from Admin + Swagger |

Document expected behaviors in README (fail-closed vs degrade).

### 24.6 Dev defaults & demo URLs

```text
# Bootstrap only — integrations from DB/Admin after boot
INFRA_PROVIDER=mock
BROKER_PROVIDER=mock
CACHE_PROVIDER=redis
LOCK_PROVIDER=redis
SESSION_PROVIDER=redis
EVENT_PROVIDER=redpanda
DOCS_ENABLED=true
ADMIN_UI_ENABLED=true
```

After `docker compose up`:
- Admin UI: `http://localhost:8000/admin`
- Swagger: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- API: `http://localhost:8000/api/v1`

`make up` / `docker compose up --build` documented in README with Local Lab checklist (all 24 parts).

### 24.7 What Docker cannot provide (and how we cover it)

| Capability | Local coverage |
|---|---|
| Real Vultr public IP | Mock IP lifecycle; optional runtime Vultr provider |
| Real broker venue | MockBrokerProvider + optional real adapter |
| Real multi-region cloud | Multi-region fields/pools in mock + config |
| ISP-level IP blacklist | Simulator `IP_BLACKLIST` profile |

---

## 25. Production Deployment (Render)

```text
Docker Image → Render Web Service (API)
            → Render Background Worker
Managed PostgreSQL
Managed Redis
Managed Kafka-compatible (or Redpanda Cloud / alternative)
Secrets via Render env (bootstrap only: DB/Redis/bus URLs, JWT, Fernet).  
Integration providers (Vultr/brokers) preferably via runtime `provider_configs` after deploy — same hot-swap model as local.

**Parity rule:** production uses the same FastAPI code, workers, Admin UI, and Swagger flags as the local lab; only managed infrastructure endpoints and active provider types differ.
```

Notes:
- Horizontal scale API instances behind load balancer
- Workers scaled independently
- Run Alembic migrations on release job
- Readiness probe `/health/ready`

---

## 26. Environment Variables

Bootstrap / platform wiring only. Integration secrets belong in `provider_configs` via Admin API.

| Variable | Example | Description |
|---|---|---|
| `APP_ENV` | `dev\|prod` | Environment |
| `DATABASE_URL` | `postgresql+asyncpg://…` | DB (bootstrap) |
| `REDIS_URL` | `redis://…` | Redis (bootstrap) |
| `REDPANDA_BROKERS` | `redpanda:9092` | Kafka API (bootstrap) |
| `JWT_SECRET` | … | JWT signing (bootstrap) |
| `SECRETS_FERNET_KEY` | … | Encrypts runtime provider/broker secrets |
| `ORDERS_EXECUTION_MODE` | `queue\|inline` | Engine mode (may also be runtime policy) |
| `LOG_LEVEL` | `INFO` | Logging |
| `DOCS_ENABLED` | `true` | Expose `/docs` and `/redoc` (assignment default true) |
| `ADMIN_UI_ENABLED` | `true` | Mount `/admin` static Operations UI |
| `INFRA_PROVIDER` | `mock` | **Fallback default only** if no active DB provider_config |
| `BROKER_PROVIDER` | `mock` | **Fallback default only** |
| `CACHE_PROVIDER` | `memory\|redis` | Fallback / bootstrap implementation hint |
| `LOCK_PROVIDER` | `memory\|redis` | Fallback |
| `SESSION_PROVIDER` | `memory\|redis` | Fallback |
| `EVENT_PROVIDER` | `memory\|redpanda` | Fallback |
| `VULTR_API_KEY` | … | **Optional legacy fallback only**; ignored when DB `provider_configs` active for infrastructure |

**Rule:** Do not require `VULTR_API_KEY` in `.env` for assignment demos. Prefer:

```http
PUT /api/v1/admin/providers/infrastructure
```

---

## 27. Testing Strategy

| Layer | Focus |
|---|---|
| Unit | Scoring, reuse policy, state machines, normalization JSON/XML, config resolution order |
| Integration | API + Postgres + Redis with memory/redpanda as needed |
| Concurrency | Dual rotate lock test; parallel orders same idempotency key |
| Failover | Timeout injection → secondary broker |
| Replay | Kill mid-submit; recover |
| Provider switch | memory↔redis event/cache smoke |
| **Provider hot-swap** | mock→vultr(mock stub with fake key path)→mock without restart; validation failure leaves prior active |
| **Local Lab** | `docker compose up` smoke: admin login, mock order, mock IP rotate, failure sim; `compose stop redis` recovery |
| Load | Locust/k6 or pytest-benchmark targeting 5k/min mock |

CI: lint + unit + integration (compose). Hot-swap tests use MockInfrastructure behind type `vultr` test double **or** wiremock; optional manual job for real Vultr.

---

## 28. Performance & Scalability (Part 24)

### 28.1 Targets

| Scale | Approach |
|---|---|
| Demo | 5k orders/min, few brokers, single region |
| Design | 50+ brokers, 100k+ orders/min |

### 28.2 Scale-Out Plan

1. **Stateless API replicas** — auth/JWT; no local queue ownership.
2. **Partitioned order topics** — key by `client_id` or `broker_id` to preserve ordering where needed.
3. **Per-broker worker pools** — isolate noisy brokers.
4. **Redis Cluster** — locks/rate limits/sessions.
5. **Postgres** — separate read replicas for monitoring; write path keep lean; partition `audit_logs`/`health_snapshots` by time.
6. **Connection pooling** — PgBouncer; httpx limits per broker.
7. **Region cells** — optional cell per region for IP pools and brokers.
8. **Backpressure** — admission control when queue depth > threshold.
9. **Caching** — capabilities, config snapshot, health scores cached with short TTL.
10. **Async offload** — never block event loop on Vultr/broker SDK; use httpx async or threadpool.

### 28.3 50+ Brokers

- Adapter registry + DB-configured accounts
- Independent health/rate limit keys
- Bulk capability refresh with jitter
- Avoid O(n) synchronous probes on request path—use cached health snapshots only

### 28.4 Resilience

- Timeouts everywhere
- Bulkheads per broker
- Failover chains
- Replay/indoubt reconciliation
- Multi-AZ Redis/Postgres
- Outbox for event durability

---

## 29. HA / DR

| Concern | Strategy |
|---|---|
| API HA | N≥2 instances |
| Worker HA | N≥2 competing consumers |
| DB | Managed Postgres with PITR backups |
| Redis | Managed HA; lock TTLs prevent deadlocks |
| Events | Replicated Kafka/Redpanda |
| DR | Document RPO/RTO; restore DB + redeploy image; replay pending |
| Region failure | Multi-region IP pools; manual/auto failover runbook |

---

## 30. Implementation Roadmap

Dependency order (not Part 1…24 linear):

| Phase | Deliverable | Maps to FRs |
|---|---|---|
| 0 | Repo skeleton, settings, logging, Docker Compose **Local Lab**, FastAPI `/docs` enabled | FR-13, PRD §16 |
| 0b | Mount Operations Admin shell at `/admin` (from sample HTML UX) + login stub + link to `/docs` | FR-13, PRD §15 |
| 1 | DB models, Alembic, repos | — |
| 2 | Provider framework + memory providers + `provider_configs` table | FR-21 foundation |
| 2b | Admin provider APIs + validate/activate/rollback + hot-reload | FR-21 |
| 3 | Auth JWT/API key/RBAC — wire Admin login to `/auth/token` | FR-12 |
| 4 | Broker accounts + capabilities + mock broker — wire Brokers page | FR-14, FR-15 |
| 5 | Sessions — wire Sessions page | FR-17 |
| 6 | Infra mock + IP allocate/attach/release — wire Static IPs / Infra pages | FR-02, FR-08 |
| 7 | Locks + assignment + reuse policy | FR-07, BR-G* |
| 8 | Whitelist normalize/sync — wire whitelist action | FR-03 |
| 9 | Health scoring — wire Broker Health page | FR-05 |
| 10 | Rate limits — wire Rate Limits page | FR-18 |
| 11 | Routing + smart policies — wire Routing / config weights | FR-01, FR-16 |
| 12 | Order engine buy/sell/cancel/status/history — wire Orders page | FR-06 |
| 13 | Failover — surface in Monitoring failovers | FR-19 |
| 14 | Zero-downtime rotation — wire rotate action in Admin | FR-04 |
| 15 | Multi-region pools | FR-20 |
| 16 | Events + outbox + Redpanda — wire Events page | FR-11 |
| 17 | Replay/recovery — wire Replay admin action | FR-22 |
| 18 | Observability + monitoring APIs — wire Dashboard/Monitoring | FR-10, FR-23 |
| 19 | Failure simulation — wire Simulator page | FR-09 |
| 20 | Dynamic config + provider credential hot-swap — wire Runtime Config page | FR-21 |
| 21 | Vultr provider | FR-08 |
| 22 | Subscription expiry teardown | FR-08 / BR-G07 |
| 23 | Docs polish + load test + Part 24 narrative; Admin↔Swagger demo checklist | FR-13, FR-24 |
| 24 | Render deploy guide (API serves `/admin` + `/docs`) | — |

---

## 31. Sequence Diagrams

### 31.1 Place Buy

```text
Client→API: POST /orders/buy
API→OrderService: place()
OrderService→DB: insert order (CREATED) unique client_order_id
OrderService→RoutingEngine: select()
RoutingEngine→Health/RateLimit/Caps: read snapshots
RoutingEngine→OrderService: broker+ip+chain
OrderService→SessionService: ensure()
OrderService→BrokerProvider: submit(ctx)
BrokerProvider→Broker: HTTP via IP
Broker→BrokerProvider: ack
OrderService→DB: update SUBMITTED + attempt
OrderService→Outbox: order.submitted
API→Client: 201 OrderResponse
```

### 31.2 IP Rotation

```text
Admin→API: rotate-ip
API→LockProvider: acquire
API→InfraProvider: allocate/attach new IP
API→Whitelist: sync
API→DB: old DRAINING
loop: wait in_flight==0
API→DB: cutover assignment + usage history
API→Events: ip.rotated
API→LockProvider: release
```

### 31.3 Failover

```text
Worker→BrokerA: submit
BrokerA: timeout
Worker→DB: attempt failed
Worker→BrokerB: submit (new attempt)
BrokerB: ack
Worker→Events: failover + order.submitted
```

### 31.4 Provider Hot-Swap (Mock → Vultr)

```text
Admin→API: PUT /admin/providers/infrastructure {vultr, api_key, validate_first=true}
API→VultrProbe: ephemeral provider.probe()
VultrProbe→API: OK
API→DB: encrypt secrets; activate version N+1; retire N
API→ProviderManager: invalidate + rebuild VultrProvider
API→EventBus: provider.activated
API→Admin: 200 masked config
Admin→API: POST /infrastructure/ips
API→ProviderManager: get_infrastructure_provider()
ProviderManager→VultrProvider: create_ip()
```

---

## 32. Operations Admin UI & Swagger

### 32.1 Goals

Provide two complementary demo surfaces on the **same FastAPI process**:

1. **`/admin`** — HTML Operations console (UX from `local/brokerbridge_operations_platform.html`) for login, analysis, and performing module actions.
2. **`/docs`** — Swagger UI for full contract testing of every `/api/v1` endpoint.

This satisfies PRD §15 without a separate Next.js app.

### 32.2 Mounting Admin static assets

```python
app.mount("/admin", StaticFiles(directory="app/static/admin", html=True), name="admin")
# or FileResponse for index + static subpaths
```

- Prefer same-origin so Admin JS calls `/api/v1/...` without CORS.
- Optional redirect: `GET /` → `/admin` in demo mode.

### 32.3 Admin client architecture (thin)

```text
app/static/admin/
  index.html          # shell: sidebar + page sections (from sample)
  js/api.js           # baseURL, Authorization header, error envelope handling
  js/auth.js          # login form → POST /api/v1/auth/token → localStorage
  js/pages/*.js       # loadBrokers(), placeOrder(), rotateIp(), activateProvider(), …
```

Rules:
- No Redux / no SPA framework required.
- Replace prototype canned JSON with real `fetch`.
- Mask secrets on GET; write-only inputs for API keys.
- Nav item **API Docs** opens `/docs` in a new tab.

### 32.4 Page → API wiring (module coverage)

| Admin page | Key endpoints | Assignment parts |
|---|---|---|
| Login | `POST /auth/token` | 12 |
| Dashboard | `GET /monitoring/*`, `/health/*` | 10, 23 |
| Brokers | `GET/POST/PATCH /brokers` | 14, 15 |
| Orders | `POST /orders/buy\|sell`, cancel, status, history | 6 |
| Routing / Runtime weights | `GET/PUT /admin/config/{key}` | 1, 16, 21 |
| Static IPs | allocate/attach/detach/release/rotate | 2, 4, 20 |
| Infrastructure | instances + auto-renew controls | 8 |
| Whitelist | sync + findings | 3 |
| Sessions | `GET /monitoring/sessions` | 17 |
| Broker Health | `GET /monitoring/brokers/health` | 5 |
| Rate Limits | `GET /monitoring/rate-limits` | 18 |
| Failovers | `GET /monitoring/failovers` | 19 |
| Events / Audit | event/audit list APIs | 11 |
| Monitoring | monitoring + metrics link | 10, 23 |
| Runtime Config / Providers | `/admin/providers/*` | 21 |
| Failure Simulator | `/admin/failure-sim/*` | 9 |
| Replay | `POST /admin/replay/run` | 22 |
| Security | API keys / roles views | 12 |
| Monitoring APIs tester | live calls (not canned) | 23 |
| Swagger link | `/docs` | 13 |

Part 7 (locks) demonstrated by concurrent rotate from UI/Swagger; Part 24 via metrics + docs narrative.

### 32.5 Admin MVP build order

1. Shell + login + `/docs` link  
2. Dashboard + health  
3. Brokers + Orders  
4. Static IPs + Infrastructure  
5. Runtime Config (provider hot-swap)  
6. Simulator + Sessions + Rate limits + Monitoring  
7. Remaining pages (events, audit, replay, whitelist, routing polish)

Wire each page as soon as its backend phase lands (see roadmap 0b + per-phase notes).

### 32.6 Swagger usage in demos

- Authorize with Bearer JWT from Admin login (or API key).
- Prefer Swagger for edge-case payloads; prefer Admin for happy-path module walkthroughs.
- README includes both URLs.

### 32.7 Local URLs

| Surface | URL |
|---|---|
| Admin | `http://localhost:8000/admin` |
| Swagger | `http://localhost:8000/docs` |
| ReDoc | `http://localhost:8000/redoc` |
| API | `http://localhost:8000/api/v1` |

---

## 33. Open Questions & Defaults

| Topic | Default Decision |
|---|---|
| Inline vs queue execution | `queue` for realism; `inline` for simple demos |
| FORCE vs ABORT rotation | Default `ABORT_ROTATION` |
| Teardown mode | Default `SUSPEND` |
| Real brokers in v1 | Mock required; one HTTP template adapter + optional one real |
| Multi-tenancy | Client-scoped data; platform admin global |
| Exactly-once wording | At-most-once confirmed submit + reconciliation |
| Vultr credentials | **Runtime `provider_configs` via Admin API/UI**; env `VULTR_API_KEY` optional legacy fallback only |
| Provider scope | Global for assignment demo; per-client overrides supported in schema |
| validate_first default | `true` for non-mock provider types |
| Bootstrap provider env | `INFRA_PROVIDER=mock`, `BROKER_PROVIDER=mock` as fallbacks when DB empty |
| Frontend | **FastAPI-hosted HTML admin** (sample UX); **no Next.js for v1** |
| API docs | **Swagger `/docs` + ReDoc enabled** for assignment demos |
| Admin auth | JWT via login form; token in `localStorage` |
| Local lab | **`docker compose up` required**; mocks default; no cloud keys required |
| Real IPs in Docker | **Not available** — use MockInfrastructureProvider; optional Vultr via Admin |
| Dependency chaos | Compose `stop`/`start` for Redis/Redpanda/API; Simulator for broker/IP faults |

---

## Appendix — Interface Skeletons

```python
class BrokerProvider(Protocol):
    async def place_order(self, ctx: BrokerRequestContext, order: OrderIntent) -> BrokerAck: ...
    async def cancel_order(self, ctx: BrokerRequestContext, broker_order_id: str) -> BrokerAck: ...
    async def get_order(self, ctx: BrokerRequestContext, broker_order_id: str) -> BrokerOrderStatus: ...
    async def list_capabilities(self) -> BrokerCapabilities: ...
    async def fetch_whitelist_raw(self) -> WhitelistRaw: ...
    async def probe_health(self) -> ProbeResult: ...

class InfrastructureProvider(Protocol):
    async def create_ip(self, region: str, **kwargs) -> IpResource: ...
    async def delete_ip(self, external_id: str) -> None: ...
    async def attach_ip(self, ip_id: str, instance_id: str) -> None: ...
    async def detach_ip(self, ip_id: str) -> None: ...
    async def create_instance(self, region: str, **kwargs) -> InstanceResource: ...
    async def destroy_instance(self, external_id: str) -> None: ...
    async def set_auto_renew(self, resource_id: str, enabled: bool) -> None: ...
    async def probe(self) -> ProbeResult: ...  # validate-then-activate

class LockProvider(Protocol):
    async def acquire(self, key: str, ttl_seconds: float, token: str) -> bool: ...
    async def release(self, key: str, token: str) -> bool: ...
    async def extend(self, key: str, token: str, ttl_seconds: float) -> bool: ...

class EventProvider(Protocol):
    async def publish(self, topic: str, event: DomainEvent) -> None: ...
    async def subscribe(self, topic: str, handler: Callable) -> None: ...
```

All swappable providers implement `probe()` (or equivalent) for Admin validation before activation.

---

## Document Control

| Version | Date | Notes |
|---|---|---|
| 0.1 / 1.0 | — | Outline drafts superseded |
| 2.0 | 2026-07-23 | Full implementation-ready TDD |
| 2.1 | 2026-07-23 | Runtime provider_configs, Admin hot-swap APIs, bootstrap vs runtime env split |
| 2.2 | 2026-07-23 | Operations Admin HTML (`/admin`) + Swagger (`/docs`); module coverage wiring + roadmap |
| 2.3 | 2026-07-23 | Local Development Lab & dual modes (Compose + mocks; real vs mocked matrix; chaos via stop/sim) |

**End of TDD**
