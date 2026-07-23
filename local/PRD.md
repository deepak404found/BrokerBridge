# Product Requirements Document (PRD)
# BrokerBridge — Broker Network Gateway & Static IP Orchestrator

| Field | Value |
|---|---|
| Product Name | BrokerBridge (working name) |
| Document Type | Product Requirements Document |
| Version | 2.3 |
| Status | Implementation-Ready |
| Audience | Engineering, Architecture, Product, Hiring Reviewers |
| Related | Assignment (24 parts), Senior Software Developer JD, TDD.md |
| Stack Context | Python 3.12, FastAPI, PostgreSQL, Redis, Redpanda, Docker, Render |

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Vision & Product Positioning](#2-vision--product-positioning)
3. [Problem Statement](#3-problem-statement)
4. [Business Objectives & Success Metrics](#4-business-objectives--success-metrics)
5. [Scope](#5-scope)
6. [Stakeholders & Personas](#6-stakeholders--personas)
7. [Product Principles](#7-product-principles)
8. [System Context & High-Level Workflows](#8-system-context--high-level-workflows)
9. [Domain Model (Business View)](#9-domain-model-business-view)
10. [Global Business Rules](#10-global-business-rules)
11. [Functional Requirements Overview](#11-functional-requirements-overview)
12. [Detailed Functional Requirements (FR-01 … FR-24)](#12-detailed-functional-requirements)
13. [Cross-Cutting Capabilities](#13-cross-cutting-capabilities)
14. [Runtime Provider Configuration (No Env / No Restart)](#14-runtime-provider-configuration-no-env--no-restart)
15. [Operations Admin UI & API Docs (Swagger)](#15-operations-admin-ui--api-docs-swagger)
16. [Local Development Lab & Dual Execution Modes](#16-local-development-lab--dual-execution-modes)
17. [User Stories](#17-user-stories)
18. [Use Cases](#18-use-cases)
19. [Decision Tables](#19-decision-tables)
20. [Edge Cases & Failure Scenarios](#20-edge-cases--failure-scenarios)
21. [Non-Functional Requirements](#21-non-functional-requirements)
22. [Security & Compliance Requirements](#22-security--compliance-requirements)
23. [Observability Requirements](#23-observability-requirements)
24. [Acceptance Criteria (Release Gate)](#24-acceptance-criteria-release-gate)
25. [Risks, Assumptions, Dependencies](#25-risks-assumptions-dependencies)
26. [Deliverables](#26-deliverables)
27. [Glossary](#27-glossary)
28. [Appendix A — Requirement Traceability Matrix](#appendix-a--requirement-traceability-matrix)
29. [Appendix B — Sample Business Payloads](#appendix-b--sample-business-payloads)

---

## 1. Executive Summary

BrokerBridge is a **production-grade middleware platform** that sits between trading clients and multiple broker APIs. It centralizes:

- Multi-broker onboarding and session lifecycle
- Smart / weighted order routing with failover
- Vultr-hosted **static IP orchestration** (allocate, attach, rotate, release)
- Broker whitelist synchronization and IP reuse policy enforcement
- Concurrent order processing with idempotency and replay
- Distributed locking, rate limiting, health scoring
- Event-driven auditability and operational monitoring
- Security (JWT, RBAC, API keys, HMAC, encrypted secrets)
- Configuration-driven **provider architecture** with **runtime hot-swap** (Admin/DB config for Vultr & brokers — no `.env` edit and no process restart for integrations)
- **Operations Admin HTML** (`/admin`) + **Swagger** (`/docs`) for demonstrating all assignment modules
- **Local Development Lab** — `docker compose up` runs the full stack with mock providers so every feature is testable without cloud/broker accounts

This document specifies **what** the product must do and **why**. Technical design (how) lives in `TDD.md`.

The assignment lists **24 parts**. They are **not** 24 independent features. They are interlocking capabilities of one cohesive distributed platform. Success is a demonstrable, deployable system that behaves like real fintech infrastructure—not a CRUD demo or an over-engineered microservice zoo.

---

## 2. Vision & Product Positioning

### 2.1 Vision

> Clients integrate once with BrokerBridge. BrokerBridge owns broker adapters, static IP infrastructure, routing intelligence, failover, security, and operations—so trading systems can scale broker diversity without scaling operational chaos.

### 2.2 Positioning

| Today (pain) | BrokerBridge (value) |
|---|---|
| Direct broker SDK coupling | Provider adapters; swap brokers via config |
| Manual static IP ops | Automated IP lifecycle + whitelist sync |
| Ad-hoc failover | Health-scored routing + exactly-once submission semantics |
| Opaque ops | Metrics, events, audit logs, monitoring APIs |
| Restart for config changes | Dynamic configuration / runtime provider reload |

### 2.3 Product Philosophy

- **Production-grade architecture**, not assignment theater
- **Provider-based** modular design
- **Configuration-driven** platform
- **Async-first** backend
- **Event-driven** communication
- **Clean Architecture / SOLID**
- **Testable, extensible, deployment-ready**

This is **not**: a CRUD app, an API demo, unrelated modules, or premature microservices.

---

## 3. Problem Statement

Trading platforms that integrate with multiple brokers face:

1. **Heterogeneous APIs** — auth, order models, error codes, rate limits differ per broker.
2. **IP whitelist constraints** — many brokers require fixed egress IPs; rotating or sharing IPs without policy causes outages and compliance risk.
3. **Operational coupling** — provisioning Vultr instances/IPs, mapping Client→Broker→IP→Order, and handling subscription expiry are manual and error-prone.
4. **Reliability gaps** — without health scoring, rate-aware routing, failover, and replay, order pipelines fail hard under broker/network faults.
5. **Security & audit debt** — credentials, HMAC signing, RBAC, and immutable audit trails are often bolted on late.
6. **Scale pressure** — concurrent order load (assignment target ~5,000 orders/min; design challenge 100k+/min) requires queues, backpressure, and horizontal scale design.

BrokerBridge addresses these as a single gateway platform with clear domain boundaries and replaceable infrastructure providers.

---

## 4. Business Objectives & Success Metrics

### 4.1 Business Objectives

| ID | Objective |
|---|---|
| BO-1 | Unify multi-broker access behind one secure API surface |
| BO-2 | Orchestrate static IP lifecycle with zero-downtime rotation |
| BO-3 | Route orders intelligently using health, latency, limits, capabilities |
| BO-4 | Guarantee auditability of IP and order lifecycle events |
| BO-5 | Survive broker/infrastructure failures via failover + replay |
| BO-6 | Allow provider/config changes without application code changes |
| BO-7 | Demonstrate senior engineering quality matching the JD bar |

### 4.2 Success Metrics (Assignment Demo + Product)

| Metric | Target |
|---|---|
| Functional coverage | All 24 assignment parts demonstrable via APIs/logs/docs |
| Order pipeline | Buy, Sell, Cancel, Status, History fully working |
| Concurrency | Sustained ~5,000 orders/min in load test (with mock brokers) |
| Idempotency | Zero duplicate broker submissions for same client order key |
| IP policy | No conflicting Client→Broker→IP assignments; reuse policy enforced |
| Failover | Automatic switch on broker-down with order completion or safe pending state |
| Config | Provider switch (mock↔vultr/real) via Admin API/UI **without** `.env` edit or restart; memory↔redis/redpanda where supported |
| Demonstrability | `/admin` UI + `/docs` Swagger cover all 24 parts (UI and/or try-it-out) |
| Observability | Prometheus metrics + structured JSON logs + monitoring APIs |
| Deploy | Docker Compose local lab (mocks) + Render-ready production path |
| Local Lab | `docker compose up` demos all 24 parts without Vultr/broker accounts |

---

## 5. Scope

### 5.1 In Scope

All assignment capabilities:

1. Dynamic Broker Routing Engine  
2. Static IP Orchestrator  
3. Broker Whitelist Synchronization  
4. Zero-Downtime IP Rotation  
5. Broker Health Scoring  
6. Concurrent Order Engine  
7. Distributed Locking  
8. Vultr Infrastructure & IP Lifecycle Management  
9. Failure Simulation  
10. Observability  
11. Event-Driven Architecture  
12. Security  
13. Architecture Documentation  
14. Multi-Broker Management  
15. Broker Capability Discovery  
16. Smart Order Routing  
17. Session Manager  
18. Rate Limit Manager  
19. Broker Failover  
20. Multi-Region Static IP Pools  
21. Dynamic Configuration  
22. Order Replay & Recovery  
23. Monitoring Dashboard APIs  
24. Design Challenge (scalability narrative + architecture support)

Plus explicit additional rules: Buy/Sell pipeline APIs; multi-broker IP management; IP allocation/reuse rules; subscription expiry behavior; full audit logging.

**Also in scope — Operations surfaces:**
- **FastAPI-hosted Operations Admin HTML UI** (`/admin`) for login, analysis, and exercising all assignment modules (UX based on `local/brokerbridge_operations_platform.html`)
- **Swagger / OpenAPI** via FastAPI built-ins (`/docs`, `/redoc`, `/openapi.json`) for API-level testing of every endpoint

**Also in scope — Local Development Lab:**
- Complete local environment via **Docker Compose only** (API, worker, PostgreSQL, Redis, Redpanda)
- Default **mock providers** so all 24 assignment parts are demonstrable without Vultr or real broker accounts
- Dual execution modes: **Local (mocks)** vs **Production/real providers** via configuration / runtime provider hot-swap — same application code

### 5.2 Out of Scope

- Trading strategies / algo engines
- Portfolio management & P&L analytics
- Exchange matching engine implementation
- **Client-facing trading UI / mobile apps** (admin ops console only)
- **Separate Next.js / React SPA product** (not required; may be considered later)
- Heavy FE stack (Redux, complex design system) — admin remains a thin HTML+JS client
- Billing/payment gateway (subscription state is an input; billing provider is external)
- Real market data fan-out as a product (may stub for health probes)

### 5.3 Future Considerations (Not Required for Assignment Pass)

- Additional broker adapters beyond mock + 1–2 sample real adapters
- Multi-tenant marketplace packaging
- Full HA multi-region active-active beyond design narrative
- Native Kubernetes operators for Vultr resources
- Optional migration of admin HTML to a thin Next.js app later

---

## 6. Stakeholders & Personas

### 6.1 Stakeholders

| Stakeholder | Interest |
|---|---|
| Trading Client / Integrator | Reliable order APIs, low latency, clear errors |
| Platform Admin | Broker onboarding, config, security, monitoring |
| Ops / SRE | Health, failover, IP rotation, incidents |
| Infra Admin | Vultr lifecycle, regions, costs, expiry |
| Support Engineer | Audit trails, order/IP history |
| Product / Hiring Reviewer | Architecture quality, completeness vs JD+assignment |

### 6.2 Personas

**P1 — API Integrator (Client System)**  
Automates order placement. Needs stable REST contracts, API keys/JWT, idempotency keys, predictable error codes.

**P2 — Platform Administrator**  
Onboards brokers, sets routing weights, manages subscriptions, triggers rotations, views monitoring APIs — primarily via **Operations Admin UI** (`/admin`) and optionally Swagger.

**P3 — Operations Engineer**  
Responds to broker-down events, validates whitelist sync, runs failure simulations in non-prod, watches Prometheus — via Admin Simulator/Monitoring pages and `/docs`.

**P5 — Hiring Reviewer / Interviewer**  
Needs a tangible path: open `/admin`, exercise modules, open `/docs` for API contract — without requiring curl expertise.
**P4 — Background Worker**  
Internal actor: processes queues, refreshes sessions, syncs whitelists, evaluates health, replays pending orders.

---

## 7. Product Principles

1. **One cohesive platform** — requirements compose; do not implement as isolated scripts.
2. **Provider boundary** — domain never imports Vultr SDK, Redis client, Kafka client, or broker SDK directly.
3. **Config over code** — provider selection and integration credentials are data, not hardcoded deploys.
4. **Bootstrap vs runtime config** — `.env` boots the platform (DB, encryption master key, JWT). Integration tools (Vultr, brokers, fault flags, routing policy) are configured at runtime via Admin APIs / DB **without editing env and without restarting** where feasible.
5. **Mock-first, real-when-ready** — defaults use mock providers so the system is demoable offline; any tester can plug in their real Vultr/broker credentials and switch live.
6. **Safety first on money path** — idempotency, locks, exactly-once submission intent, audit.
7. **Fail closed on expiry** — expired subscription → no trading + infra teardown policy.
8. **Observable by default** — every critical path emits metrics/events/logs.
9. **Demo realism** — mock providers must exercise the same workflows as real ones.
10. **Demonstrable ops surfaces** — FastAPI-hosted Admin HTML + Swagger so every module can be tested without curl-only workflows.
11. **Local-first lab** — clone + `docker compose up` must exercise the full platform with mocks; real providers are optional and config-driven.

---

## 8. System Context & High-Level Workflows

### 8.1 Context Diagram (Logical)

```text
[Client Systems] --REST/JWT/APIKey/HMAC--> [BrokerBridge API]
                                              |
                     +------------------------+------------------------+
                     |                        |                        |
              [PostgreSQL]              [Redis Cache/Lock/Session] [Redpanda Events]
                     |
              [Provider Manager]
                     |
     +---------------+---------------+----------------+
     |               |               |                |
 [BrokerProvider] [InfraProvider] [EventProvider] [Cache/Lock/Session Providers]
     |               |
 [Brokers]       [Vultr]
```

### 8.2 Primary Business Workflow — Place Order

```text
Client → Authenticate → Validate order + subscription active
      → Resolve eligible brokers (capability, region, rate limit, health)
      → Smart route / weighted select
      → Ensure session valid
      → Ensure assigned static IP (or allocate per policy)
      → Acquire distributed lock if IP-sensitive mutation needed
      → Submit via BrokerProvider bound to assigned IP
      → Persist order state + audit
      → Publish events (order.created / order.submitted / …)
      → Return response (accepted / filled / rejected / pending)
```

### 8.3 Primary Business Workflow — Zero-Downtime IP Rotation

```text
Admin/System → Request rotate(broker_id)
            → Acquire Redis lock for broker/IP resource
            → Allocate/select new IP from region pool
            → Attach new IP; update whitelist sync (pending→active)
            → Drain: wait for in-flight orders on old IP to complete (timeout policy)
            → Switch assignment mapping to new IP
            → Detach/release old IP per reuse policy
            → Audit + events (ip.allocated, ip.rotated, ip.released)
            → Release lock
```

### 8.4 Subscription Expiry Workflow

```text
Scheduler detects subscription expired
 → Block new orders for client
 → Cancel/queue-safe handling for pending orders per policy
 → Stop Vultr auto-renewal
 → Suspend or destroy infrastructure per config
 → Release/rotate IPs as required
 → Publish subscription.expired + audit
```

---

## 9. Domain Model (Business View)

### 9.1 Core Entities

| Entity | Description |
|---|---|
| Client | Tenant that owns brokers, subscriptions, API credentials |
| BrokerAccount | Onboarded broker connection for a client (credentials ref, capabilities, priority) |
| BrokerProviderType | Adapter identity (mock, zerodha, angelone, ibkr, …) |
| Session | Broker auth session/token with expiry and refresh metadata |
| StaticIP | Vultr (or mock) public IP resource with region, status, health |
| Instance | Compute instance optionally backing IP attachment |
| IPAssignment | Binding Client + BrokerAccount ↔ StaticIP with lifecycle state |
| WhitelistRecord | Normalized broker-side allowlist entry for an IP |
| Order | Buy/Sell intent and execution state machine |
| OrderAttempt | Submission attempt to a broker (supports failover/replay) |
| HealthSnapshot | Periodic broker/IP health metrics and composite score |
| RateLimitBucket | Per-broker/client quota tracking |
| Subscription | Commercial entitlement controlling trading + infra |
| AuditLog | Immutable record of critical actions |
| DomainEvent | Published integration event |
| ConfigurationItem | Dynamic config key/value with version and scope |
| ProviderConfig | Runtime provider selection + encrypted integration secrets (global or per-client) |

### 9.2 Canonical Mapping (Assignment Mandate)

**Client → BrokerAccount → Assigned StaticIP → Order**

Every order execution record must reference the IP that was assigned at submission time.

### 9.3 Order State Machine (Business)

```text
CREATED → VALIDATED → ROUTED → SUBMITTING → SUBMITTED
                              ↘ FAILED_RETRYABLE → (failover/replay) → SUBMITTING
SUBMITTED → PARTIAL → FILLED
         → REJECTED
         → CANCEL_PENDING → CANCELLED
         → EXPIRED / DEAD_LETTER (ops review)
```

Idempotency key (`client_order_id`) uniquely identifies an order per client.

---

## 10. Global Business Rules

| ID | Rule |
|---|---|
| BR-G01 | Every order **must** be routed through the broker's **currently assigned** static IP. |
| BR-G02 | A client may own **any number** of brokers. |
| BR-G03 | A single static IP **may be shared** across multiple brokers. |
| BR-G04 | Once an IP has been assigned/used for a **specific broker**, it **must not** be reassigned to that **same broker** until released or rotated per **configured reuse policy**. |
| BR-G05 | System must prevent duplicate/conflicting IP assignments. |
| BR-G06 | Record every IP allocation, release, rotation, and order execution in an **audit log**. |
| BR-G07 | On subscription expiry: **disable trading**, **stop Vultr auto-renewal**, **suspend/destroy** infrastructure, **block new orders**. |
| BR-G08 | Duplicate broker execution for the same client order is **prohibited** (idempotency / exactly-once submission intent). |
| BR-G09 | Health score, latency, success rate, priority, capabilities, and rate limits **influence** routing. |
| BR-G10 | Critical mutations on IP rotation require **distributed locks**. |
| BR-G11 | Provider implementations are selected by **configuration**, not hardcoded imports in domain services. |
| BR-G12 | Secrets (broker credentials, API keys, Vultr tokens) are stored **encrypted**; never logged in plaintext. |
| BR-G13 | Changing integration provider type or credentials (e.g. mock→Vultr) **must not** require `.env` edits or process restart when the provider supports hot-swap. |
| BR-G14 | Provider activation follows **validate → stage → activate** (optional rollback to previous version). Invalid credentials must not replace a working active provider. |
| BR-G15 | Bootstrap env vars configure platform connectivity only; they are **not** the primary store for Vultr/broker integration secrets in normal operation. |

---

## 11. Functional Requirements Overview

| FR | Assignment Part | Title |
|---|---|---|
| FR-01 | Part 1 | Dynamic Broker Routing Engine |
| FR-02 | Part 2 | Static IP Orchestrator |
| FR-03 | Part 3 | Broker Whitelist Synchronization |
| FR-04 | Part 4 | Zero-Downtime IP Rotation |
| FR-05 | Part 5 | Broker Health Scoring |
| FR-06 | Part 6 | Concurrent Order Engine |
| FR-07 | Part 7 | Distributed Locking |
| FR-08 | Part 8 | Vultr Infrastructure & IP Lifecycle |
| FR-09 | Part 9 | Failure Simulation |
| FR-10 | Part 10 | Observability |
| FR-11 | Part 11 | Event-Driven Architecture |
| FR-12 | Part 12 | Security |
| FR-13 | Part 13 | Architecture Documentation |
| FR-14 | Part 14 | Multi-Broker Management |
| FR-15 | Part 15 | Broker Capability Discovery |
| FR-16 | Part 16 | Smart Order Routing |
| FR-17 | Part 17 | Session Manager |
| FR-18 | Part 18 | Rate Limit Manager |
| FR-19 | Part 19 | Broker Failover |
| FR-20 | Part 20 | Multi-Region Static IP Pools |
| FR-21 | Part 21 | Dynamic Configuration |
| FR-22 | Part 22 | Order Replay & Recovery |
| FR-23 | Part 23 | Monitoring Dashboard APIs |
| FR-24 | Part 24 | Scalability Design Challenge |

---

## 12. Detailed Functional Requirements

Each FR below includes: description, actors, business logic, inputs/outputs, rules, edge cases, failure handling, and acceptance criteria.

---

### FR-01 — Dynamic Broker Routing Engine (Part 1)

**Description**  
Maintain multiple broker connections and associated static IPs. Route orders using weighted routing based on latency, success rate, broker priority, IP health, and automatic failover eligibility.

**Actors**  
Client, Routing Engine, Health Service, Rate Limit Manager, Session Manager.

**Business Logic**
1. Build candidate set: brokers owned by client, enabled, subscription OK, capability match, session usable or refreshable, IP assigned or allocatable, rate limit not exhausted (or queueable).
2. Score candidates using weighted formula (see Decision Tables).
3. Select primary + ordered failover list.
4. Persist routing decision on the order attempt for audit.
5. If no candidate: reject with `NO_ROUTE` and actionable reason codes.

**Inputs**  
Order intent, client_id, instrument, side, quantity, optional broker preference, region preference.

**Outputs**  
Selected broker_id, ip_id, route_score, failover_chain.

**Acceptance Criteria**
- [ ] Given 3 healthy brokers with different scores, highest score is selected unless sticky preference overrides.
- [ ] Unhealthy brokers (score below threshold) are excluded unless emergency override configured.
- [ ] Routing decision is auditable and returned in internal logs/events.

---

### FR-02 — Static IP Orchestrator (Part 2)

**Description**  
Allocate, release, attach, detach, and rotate static IPs behind an infrastructure abstraction (mock or Vultr).

**Business Logic**
- `allocate(region, tags)` → create/reserve IP
- `attach(ip, instance|broker_context)` → bind for egress use
- `detach(ip)` → unbind without necessarily destroying
- `release(ip)` → return to pool / destroy per provider
- `rotate(broker)` → orchestrated cutover (FR-04)

**States**  
`AVAILABLE → ALLOCATED → ATTACHED → DRAINING → DETACHED → RELEASED` (plus `QUARANTINED` for blacklist/simulation)

**Rules**  
BR-G01–G06 apply. Allocation must create audit + event `ip.allocated`.

**Acceptance Criteria**
- [ ] All IP lifecycle ops work via admin/API with mock provider.
- [ ] Domain services call InfrastructureProvider only—no direct Vultr API calls.
- [ ] Mapping Client→Broker→IP is consistent after each operation.

---

### FR-03 — Broker Whitelist Synchronization (Part 3)

**Description**  
Normalize broker whitelist formats (JSON/XML and future formats), detect missing, duplicate, stale, and unauthorized IPs.

**Business Logic**
1. Fetch broker whitelist via BrokerProvider capability (or mock fixture).
2. Normalize to canonical `{ip, status, last_seen, source_format}`.
3. Diff against assigned IPs for that broker.
4. Classify: `MISSING`, `DUPLICATE`, `STALE`, `UNAUTHORIZED`, `OK`.
5. Emit findings; optionally auto-remediate if configured (request add/remove).

**Acceptance Criteria**
- [ ] JSON and XML sample inputs normalize to identical canonical records.
- [ ] Diff detects missing assigned IP and unauthorized extra IP.
- [ ] Sync job is schedulable and results visible via monitoring API.

---

### FR-04 — Zero-Downtime IP Rotation (Part 4)

**Description**  
Rotate IPs without interrupting in-flight orders.

**Business Logic**
1. Lock broker IP resource (FR-07).
2. Allocate/attach new IP; begin whitelist propagation.
3. Mark old IP `DRAINING`; new orders use new IP only after cutover gate.
4. Wait until in-flight order count on old IP = 0 or timeout.
5. On success: cutover assignment; detach/release old IP per reuse policy.
6. On timeout: policy = `FORCE_CUTOVER` | `ABORT_ROTATION` (config).

**Acceptance Criteria**
- [ ] In-flight orders on old IP complete successfully during drain.
- [ ] New orders after cutover use new IP exclusively.
- [ ] Concurrent rotation attempts for same broker are serialized by lock.

---

### FR-05 — Broker Health Scoring (Part 5)

**Description**  
Compute broker health using latency, connectivity, timeout rate, and success metrics.

**Suggested Composite Score (0–100)**  
```
score = w_lat * latency_score
      + w_succ * success_rate_score
      + w_conn * connectivity_score
      + w_to * (1 - timeout_rate_score)
      + w_ip * ip_health_score
```
Weights are configurable (FR-21). Thresholds: `HEALTHY`, `DEGRADED`, `UNHEALTHY`.

**Acceptance Criteria**
- [ ] Continuous probe updates health snapshots.
- [ ] Routing excludes `UNHEALTHY` by default.
- [ ] Score breakdown queryable via monitoring API.

---

### FR-06 — Concurrent Order Engine (Part 6)

**Description**  
Support ~5,000 orders/min using asyncio, queues, retries, exponential backoff, and idempotency.

**Business Logic**
- Ingress API enqueues validated orders quickly (accept + async process OR bounded sync with worker offload).
- Worker pool pulls from queue with concurrency limits per broker.
- Retries use exponential backoff + jitter for retryable errors.
- Idempotency key prevents duplicate submission.
- Backpressure: reject or queue with `QUEUE_FULL` when saturated.

**Acceptance Criteria**
- [ ] Load test with mock brokers sustains ~5k orders/min without process crash.
- [ ] Duplicate `client_order_id` returns prior order—does not double-submit.
- [ ] Retryable failures backoff; non-retryable fail fast.

---

### FR-07 — Distributed Locking (Part 7)

**Description**  
Prevent concurrent IP rotation (and other critical sections) using Redis-based distributed locking (MemoryLock in local/dev).

**Critical Sections**
- IP rotate / allocate conflict checks
- Assignment mutations
- Possibly session refresh stampedes (optional)

**Lock Properties**  
Keyed by resource (`lock:broker:{id}:ip`), TTL, fencing token / ownership token, safe unlock.

**Acceptance Criteria**
- [ ] Two concurrent rotate calls: one proceeds, one waits or fails with `LOCK_HELD`.
- [ ] Lock auto-expires on crash after TTL; no permanent deadlock under test.
- [ ] LockProvider swappable memory↔redis via config.

---

### FR-08 — Vultr Infrastructure & IP Lifecycle (Part 8)

**Description**  
Provision/terminate Vultr instances, manage public IPs, maintain Client→Broker→Instance→IP mapping, stop auto-renewal on expiry, suspend/destroy infrastructure, prevent trading after expiry.

**Business Logic**
- InfraProvider APIs: create_instance, destroy_instance, create_ip, delete_ip, attach, detach, set_auto_renew(false)
- Mapping tables always updated transactionally with audit
- Subscription expiry orchestrates teardown (BR-G07)

**Acceptance Criteria**
- [ ] MockInfrastructureProvider simulates full lifecycle.
- [ ] VultrProvider implements same interface (real calls behind adapter).
- [ ] Expiry path stops auto-renewal and blocks trading.

---

### FR-09 — Failure Simulation (Part 9)

**Description**  
Simulate broker timeout, DNS failures, TLS failures, IP blacklisting, and recovery—for testing resilience.

**Business Logic**
Admin API enables fault injection profiles on mock (and optionally staging) providers:
- `BROKER_TIMEOUT`, `DNS_FAIL`, `TLS_FAIL`, `IP_BLACKLIST`, `PARTIAL_OUTAGE`
- Recovery clears injection and publishes recovery events

**Acceptance Criteria**
- [ ] Enabling timeout causes routing/failover behavior to trigger.
- [ ] Blacklist marks IP quarantined and excludes from routing.
- [ ] Recovery restores healthy path; events emitted.

---

### FR-10 — Observability (Part 10)

**Description**  
Expose Prometheus metrics and structured JSON logs.

**Minimum Metrics**
- order_submit_total{broker,status}
- order_latency_seconds{broker}
- broker_health_score{broker}
- ip_rotation_total{result}
- failover_total{from,to}
- queue_depth
- rate_limit_hits_total

**Logs**  
JSON fields: timestamp, level, request_id, client_id, broker_id, order_id, event, error_code.

**Acceptance Criteria**
- [ ] `/metrics` scrapable by Prometheus.
- [ ] Request logs are JSON and correlatable by `request_id`.

---

### FR-11 — Event-Driven Architecture (Part 11)

**Description**  
Publish domain events such as IPAllocated, BrokerDown, OrderSucceeded via EventProvider (Memory or Redpanda).

**Core Events** (non-exhaustive)  
`order.created`, `order.submitted`, `order.succeeded`, `order.failed`, `broker.down`, `broker.recovered`, `ip.allocated`, `ip.rotated`, `ip.released`, `subscription.expired`, `session.refreshed`, `whitelist.sync.completed`

**Acceptance Criteria**
- [ ] Critical lifecycle actions publish events.
- [ ] Switching EVENT_PROVIDER does not change domain code.
- [ ] Consumers (audit projector / metrics) can subscribe in-process or via Redpanda.

---

### FR-12 — Security (Part 12)

**Description**  
JWT, RBAC, API Keys, encrypted configuration, HMAC signing, secret rotation.

**Requirements**
- AuthN: JWT bearer and/or API key
- AuthZ: RBAC roles (`client`, `admin`, `ops`, `readonly`)
- HMAC request signing for sensitive routes (configurable)
- Secrets encrypted at rest (envelope encryption / Fernet or KMS-ready interface)
- Secret rotation procedure without downtime (dual-key accept window)

**Acceptance Criteria**
- [ ] Unauthorized requests rejected.
- [ ] Role-gated admin routes enforced.
- [ ] Secrets never appear in logs or metrics labels.

---

### FR-13 — Architecture Documentation (Part 13)

**Description**  
Provide architecture, HA/DR, monitoring, scaling, and security documentation. Also expose interactive API documentation (Swagger/OpenAPI) and an Operations Admin UI for demonstrability.

**Deliverables**  
This PRD, `TDD.md`, README, ERD, sequence diagrams, deployment guide, HA/DR notes (in TDD), **Swagger UI** (`/docs`), **ReDoc** (`/redoc`), **Operations Admin HTML** (`/admin`).

**Acceptance Criteria**
- [ ] Docs sufficient for a new senior engineer to implement/operate without tribal knowledge.
- [ ] HA/DR and scale narrative addresses Part 24.
- [ ] `/docs` Swagger UI lists and allows trying all public `/api/v1` endpoints.
- [ ] `/admin` Operations UI is served by the FastAPI app and covers module testing (see §15).

---

### FR-14 — Multi-Broker Management (Part 14)

**Description**  
Onboard unlimited brokers without code changes using adapters + metadata/config.

**Business Logic**
- Register broker account with provider type + credentials ref + capabilities + priority + region constraints
- New provider types added by registering adapter class in provider registry (code once per broker family; instances unlimited via config/DB)

**Acceptance Criteria**
- [ ] Two broker accounts of same provider type coexist for one client.
- [ ] Disable broker removes it from routing without deploy.
- [ ] Adding a new account requires no routing code changes.

---

### FR-15 — Broker Capability Discovery (Part 15)

**Description**  
Use metadata (order types, markets, instruments, short-sell, after-hours, etc.) for routing decisions.

**Acceptance Criteria**
- [ ] Order requiring capability X is not routed to broker lacking X.
- [ ] Capabilities queryable via broker APIs.
- [ ] Capability updates via dynamic config/discovery refresh.

---

### FR-16 — Smart Order Routing (Part 16)

**Description**  
Route dynamically using health, latency, limits, and capabilities (complements FR-01 with fuller policy).

**Policies** (config)
- `WEIGHTED_SCORE` (default)
- `LOWEST_LATENCY`
- `HIGHEST_PRIORITY_HEALTHY`
- `STICKY_BROKER` (if specified and eligible)

**Acceptance Criteria**
- [ ] Policy switch changes selection without code change.
- [ ] Rate-limited broker skipped or queued per policy.
- [ ] Capability mismatch excluded.

---

### FR-17 — Session Manager (Part 17)

**Description**  
Centralized token refresh with encrypted credential storage.

**Business Logic**
- Get valid session for broker; refresh if near expiry
- Single-flight refresh per broker (lock/cache)
- Store tokens in SessionProvider (memory/redis) with encryption for secrets at rest in DB

**Acceptance Criteria**
- [ ] Concurrent orders share one refresh—no thundering herd.
- [ ] Expired session triggers refresh before submit.
- [ ] Credentials encrypted in persistence.

---

### FR-18 — Rate Limit Manager (Part 18)

**Description**  
Track quotas, queue requests, and reroute when limits are exceeded.

**Business Logic**
- Token bucket / sliding window per broker (and optionally per client)
- On exceed: `REROUTE` | `QUEUE` | `REJECT` per config
- Emit `rate_limit_hits` metric

**Acceptance Criteria**
- [ ] Exceeding limit triggers configured behavior.
- [ ] Monitoring API shows remaining quota.
- [ ] Reroute selects next eligible broker.

---

### FR-19 — Broker Failover (Part 19)

**Description**  
Automatic broker switching with exactly-once submission semantics.

**Business Logic**
1. Detect failure (timeout, 5xx, broker.down health).
2. If order not confirmed submitted → try next broker in failover chain with **same idempotency key / submission token**.
3. If submission uncertain → enter `INDOUBT` reconciliation path (query status / replay-safe).
4. Never double-submit when broker ack received.

**Acceptance Criteria**
- [ ] Simulated broker timeout fails over to secondary.
- [ ] Confirmed submit does not resubmit elsewhere.
- [ ] Indoubt path reconciles without duplicate fill intent.

---

### FR-20 — Multi-Region Static IP Pools (Part 20)

**Description**  
Support multiple regions while respecting broker/IP constraints.

**Rules**
- Pools keyed by region
- Broker may restrict allowed regions
- Routing prefers matching region; fallback only if policy allows

**Acceptance Criteria**
- [ ] Allocate from specified region pool.
- [ ] Broker with region constraint never assigned out-of-region IP.
- [ ] Monitoring shows pool capacity per region.

---

### FR-21 — Dynamic Configuration (Part 21)

**Description**  
Apply broker, provider, and policy configuration changes **without process restart** and **without requiring `.env` changes** for integration tools. The platform boots with safe defaults (typically mocks). Operators and testers then configure real services (Vultr, broker adapters, policies) through authenticated Admin APIs. Secrets are stored encrypted in the database and hot-loaded by `ProviderManager`.

**Two config planes**

| Plane | Stored in | Examples | Restart required? |
|---|---|---|---|
| **Bootstrap** | Environment / secret manager | `DATABASE_URL`, `REDIS_URL`, `SECRETS_FERNET_KEY`, `JWT_SECRET` | Yes (process start) |
| **Runtime** | DB (`configuration_items`, `provider_configs`) | Infra provider mock↔vultr + API key, broker credentials, routing weights, rate limits, fault injection, teardown modes | **No** for supported keys |

**Runtime-configurable integrations (must support hot-swap)**
- Infrastructure provider: `mock` ↔ `vultr` (+ API key, default region, account options)
- Broker provider selection / per-account credentials and enable flags
- Routing weights, health thresholds, rate-limit policies
- IP reuse / rotation / subscription teardown policies
- Fault injection profiles
- Optional: Event/Cache/Lock/Session **logical** switches where safe (memory↔redis may be restricted in prod; see TDD)

**Business Logic**
1. Admin submits provider config via API (`validate_first` recommended).
2. System decrypts nothing in logs; encrypts secrets at rest with platform Fernet/KMS key from bootstrap env.
3. Optional connectivity probe (e.g. Vultr account ping) before activation.
4. On success: version bump, activate config, invalidate ProviderManager cache, publish `config.updated` / `provider.activated`.
5. All API/worker instances refresh in-memory snapshot (pubsub or short poll).
6. Subsequent calls use the new provider instance—**no redeploy**.
7. Rollback restores previous version atomically.

**Scope modes**
- **Global** (default for assignment demo): one active infra provider for the deployment.
- **Per-client override** (supported design): Client A uses Vultr with their key; Client B stays on mock.

**Actors**  
Platform Admin, Ops (read/test), System (reload fans-out).

**Acceptance Criteria**
- [ ] Fresh deploy works entirely on mock providers with no Vultr/broker secrets in `.env`.
- [ ] Admin can switch infrastructure provider from `mock` to `vultr` by API with API key in body; **no** `.env` edit and **no** server restart; subsequent IP allocate uses Vultr.
- [ ] Admin can switch back to `mock` the same way.
- [ ] Failed validation (`validate_first=true`) leaves the previous active provider unchanged.
- [ ] Update routing weight via admin API; subsequent routes use new weight without restart.
- [ ] Config/provider versions audited (secret values redacted).
- [ ] Invalid config rejected with validation errors.
- [ ] Encrypted secrets never appear in logs, metrics labels, or GET responses (masked).

---

### FR-22 — Order Replay & Recovery (Part 22)

**Description**  
Recover pending orders after restart without duplicates.

**Business Logic**
- Persist durable order + attempt state before broker submit acknowledgment stages
- On startup, worker scans `SUBMITTING` / `PENDING` / `INDOUBT` and resumes safely
- Idempotency keys + broker status query prevent duplicates

**Acceptance Criteria**
- [ ] Kill process mid-queue; restart completes pending without duplicate submits (mock verified).
- [ ] Dead-letter path for unrecoverable orders.
- [ ] Replay run emits audit events.

---

### FR-23 — Monitoring Dashboard APIs (Part 23)

**Description**  
Expose APIs for broker health, sessions, IP health, failovers, and rate limits. These APIs power both Swagger testing and the Operations Admin HTML dashboard pages.

**Minimum Endpoints** (shapes finalized in TDD)
- Broker health list/detail
- Session status
- IP pool/assignment health
- Recent failovers
- Rate limit snapshots
- Queue depth / order engine stats

**Acceptance Criteria**
- [ ] Authenticated ops/admin can fetch all monitoring resources.
- [ ] Data matches underlying metrics within acceptable lag.
- [ ] Admin UI Monitoring / Dashboard pages consume these APIs (not hardcoded mock stats in production mode).

---

### FR-24 — Scalability Design Challenge (Part 24)

**Description**  
Explain and architect support for 50+ brokers, 100k+ orders/min, resilience and scalability.

**Product Requirement**  
Documented, credible design (in TDD) covering: horizontal API scale, partitioned workers, broker isolation queues, Redis/Redpanda partitioning, DB write strategies, backpressure, regional pools, cell architecture optional. Implementation for assignment may demonstrate at 5k/min with clear path to 100k/min.

**Acceptance Criteria**
- [ ] TDD includes scalability section addressing 50+ brokers and 100k+/min.
- [ ] Code structure does not preclude horizontal scale (stateless API).

---

## 13. Cross-Cutting Capabilities

### 13.1 Buy/Sell Pipeline APIs

| API | Behavior |
|---|---|
| Place Buy | Create buy order; route; submit; return status |
| Place Sell | Create sell order; same pipeline |
| Cancel Order | Cancel if cancellable; broker cancel via assigned IP |
| Order Status | Current state + attempts + broker refs |
| Order History | Filtered list with pagination |

### 13.2 Auditability

Every critical mutation writes AuditLog: actor, action, entity, before/after, request_id, timestamp.

### 13.3 Provider Runtime Matrix

| Concern | Default (ship/demo) | Runtime switch target | Hot-swap without restart? |
|---|---|---|---|
| Broker adapters | mock | real broker types + credentials | **Yes** (per account / registry) |
| Infrastructure | mock | Vultr (+ API key, region) | **Yes** (primary demo path) |
| Cache | memory or redis | redis | Prefer yes in dev; prod URL change = restart |
| Lock | memory or redis | redis | Prefer yes in dev; prod URL change = restart |
| Session | memory or redis | redis | Prefer yes in dev; prod URL change = restart |
| Event | memory or redpanda | redpanda | Dual-publish / rolling preferred for prod bus URL |

**Product rule:** Testers must be able to exercise **real Vultr** and **real broker** integrations by submitting credentials through Admin APIs while the process keeps running. Bootstrap env must not be required for those secrets in normal flows.

---

## 14. Runtime Provider Configuration (No Env / No Restart)

### 14.1 Problem this solves

Hardcoding `VULTR_API_KEY` (or similar) only in `.env` forces every tester to edit deploy config and restart. That blocks “try my real account” demos and violates FR-21.

### 14.2 Desired operator journey

```text
1. Start BrokerBridge (Compose / Render) — mocks active by default
2. Admin authenticates
3. PUT provider config: type=vultr + api_key + region (validate_first=true)
4. System probes Vultr → activates → ProviderManager rebuilds InfraProvider
5. Allocate / rotate IPs against real Vultr
6. Optionally onboard real broker credentials the same way
7. PUT provider type=mock to revert — still no restart
```

### 14.3 What stays in `.env` (bootstrap only)

- Database / Redis / Redpanda connection strings (platform wiring)
- `SECRETS_FERNET_KEY` (or KMS ref) to encrypt runtime secrets at rest
- `JWT_SECRET` (or signing keys)
- Optional **legacy fallback** env for infra/broker secrets (dev convenience only; runtime DB config wins when present)

### 14.4 What lives in runtime DB config

- Active provider type per kind (`infrastructure`, `broker` defaults, etc.)
- Vultr API key, default region, optional project/account metadata
- Broker adapter credentials (also on `broker_accounts`)
- Policy knobs: routing, rate limits, IP reuse, rotation, teardown, fault injection

### 14.5 Safety requirements

| Requirement | Behavior |
|---|---|
| Validate-then-activate | Probe before cutover when `validate_first=true` |
| Versioned history | Keep N previous versions for rollback |
| Redaction | GET APIs return `api_key: "***"` only |
| RBAC | Only `admin` (and optionally `ops` for test endpoint) |
| Audit | Record actor, kind, type, version — never raw secret |
| Scope | Global and/or per-client override |

### 14.6 Success metric

A reviewer with only Admin API access can switch mock→Vultr→mock and mock→real-broker credentials on a running instance without SSH, without `.env` edits, and without restarting the service.

---

## 15. Operations Admin UI & API Docs (Swagger)

### 15.1 Decision

BrokerBridge ships a **FastAPI-hosted Operations Admin HTML UI** plus **built-in Swagger/OpenAPI**.  

- **Admin UI** = primary demo surface for interviewers (login, analyze, perform actions).  
- **Swagger** = complete API contract + try-it-out for every endpoint.  
- **Not** a separate Next.js app for v1.

UX/visual baseline: `local/brokerbridge_operations_platform.html` (sidebar ops console). Implementation evolves that shell into a thin HTML+JS client that calls real `/api/v1` APIs (no hardcoded production metrics).

### 15.2 Serving model

| Surface | URL | Purpose |
|---|---|---|
| Operations Admin | `/admin` (and `/admin/…`) | Login + module demos |
| Swagger UI | `/docs` | Interactive API testing (FastAPI default) |
| ReDoc | `/redoc` | Readable OpenAPI |
| OpenAPI schema | `/openapi.json` | Machine-readable contract |
| REST API | `/api/v1/…` | System of record for UI and Swagger |

Same FastAPI process serves API + static admin + docs. No separate FE deploy required for the assignment.

### 15.3 Admin capabilities (must cover all assignment parts)

Every Part 1–24 must be exercisable via **Admin UI and/or Swagger**, with Admin covering the operational happy paths:

| Admin page / action | Assignment parts | Primary APIs |
|---|---|---|
| Login / role session | 12 | `/auth/token` |
| Dashboard | 10, 23 | `/monitoring/*`, `/health/*` |
| Clients | 8 (subscription view) | client/subscription APIs |
| Brokers (onboard/enable/capabilities) | 14, 15 | `/brokers` |
| Routing policy / weights | 1, 16 | `/admin/config`, routing views |
| Orders (buy/sell/cancel/status/history) | 6 + buy/sell pipeline | `/orders/*` |
| Static IPs (allocate/rotate/release) | 2, 4, 20 | `/infrastructure/ips*` |
| Infrastructure lifecycle | 8 | `/infrastructure/instances*` |
| Whitelist sync | 3 | whitelist sync endpoints |
| Sessions | 17 | `/monitoring/sessions` |
| Broker Health | 5 | `/monitoring/brokers/health` |
| Rate Limits | 18 | `/monitoring/rate-limits` |
| Failover visibility | 19 | `/monitoring/failovers` |
| Events / audit stream | 11 | events + audit APIs |
| Monitoring | 10, 23 | `/monitoring/*`, `/metrics` |
| Runtime Config + provider hot-swap | 21 | `/admin/config`, `/admin/providers/*` |
| Failure Simulator | 9 | `/admin/failure-sim/*` |
| Replay / recovery trigger | 22 | `/admin/replay/run` |
| Security settings (keys/roles view) | 12 | auth admin endpoints |
| Link to Swagger / OpenAPI | 13 | `/docs`, `/redoc` |
| Scalability / metrics narrative | 24 | `/metrics` + docs |

Distributed locking (Part 7) is demonstrated via concurrent rotate attempts in Admin + documented behavior (not a separate page required).

### 15.4 UX requirements

- Visual language aligned with sample HTML (dark ops console, sidebar nav, status badges, tables, charts where useful).
- Simple login (JWT stored client-side; optional API-key paste for demos).
- Header/nav link: **API Docs → `/docs`**.
- Actions that mutate state call real APIs and show success/error toasts from API envelopes.
- Secrets in Runtime Config forms are write-only; reads show masked values.
- Pages may load progressively: shell first, then wire APIs as backend modules land (MVP order in TDD).

### 15.5 Swagger requirements

- FastAPI auto-generated OpenAPI **must remain enabled** for assignment demos (`docs_url="/docs"`, `redoc_url="/redoc"`).
- All public routers tagged (orders, brokers, infrastructure, monitoring, admin, auth, health).
- Request/response schemas via Pydantic so Swagger is accurate.
- Optional later: protect `/docs` behind admin auth in hardened prod; default for assignment is **open docs** on local/demo.

### 15.6 Explicit non-goals for Admin UI

- Not a client trading application.
- Not a separate React/Next.js codebase for v1.
- No Redux / complex FE architecture — thin `fetch` + page scripts.
- Pixel-perfect product design is not a grading target; **module coverage + clarity** is.

### 15.7 Acceptance criteria (Admin + Docs)

- [ ] `/admin` served by FastAPI without a separate FE server.
- [ ] User can log in and exercise brokers, orders, IPs, runtime provider config, and failure simulation from the UI.
- [ ] Every assignment part has a documented Admin and/or Swagger demo path.
- [ ] `/docs` lists and executes authenticated API calls successfully against a running stack.
- [ ] Admin UI does not rely on canned fake metrics once corresponding APIs exist.

---

## 16. Local Development Lab & Dual Execution Modes

### 16.1 Goal

BrokerBridge must provide a **complete local development and demo environment** where every assignment feature can be developed, tested, and demonstrated **without** real cloud infrastructure or broker accounts.

A developer or reviewer should be able to:

```bash
git clone <repo>
docker compose up --build
```

Then open `/admin` and `/docs` and exercise the full platform.

### 16.2 Compose stack (assignment scope only)

Docker Compose includes **only** stack services required by the architecture:

| Service | Role |
|---|---|
| `api` | FastAPI + `/admin` + `/docs` |
| `worker` | Order/health/sync/replay/expiry jobs |
| `postgres` | System of record |
| `redis` | Cache, locks, sessions, rate limits |
| `redpanda` | Kafka-compatible event bus |

**Do not** introduce extra infra outside assignment scope (no Elastic, MinIO, full K8s-in-Docker, etc.) unless later justified.

### 16.3 What is real locally vs mocked

| Real in Docker (shared platform) | Mocked locally (external world) |
|---|---|
| FastAPI, Admin UI, Swagger | Real broker HTTP APIs |
| PostgreSQL | Vultr API / real public static IPs |
| Redis (cache/lock/session/rate limit) | Real broker whitelist endpoints |
| Redpanda events | Cloud DNS/TLS failures (unless simulated) |
| JWT, RBAC, routing, orders, health, replay, monitoring | — |

**Static IP allocation locally:** `MockInfrastructureProvider` simulates allocate/attach/detach/release/rotate using documentation IP ranges (e.g. `198.51.100.0/24`, `203.0.113.0/24`), full mapping/audit/events. True ISP-routable Vultr IPs require the real `VultrProvider` (optional via runtime config).

Business logic, services, repositories, and APIs are **identical** in both modes; only provider adapters differ.

### 16.4 Local mock provider requirements

Default local providers must simulate all behaviors needed by the assignment:

- Broker responses, order execution, cancel/status/history
- Session create/expire/refresh
- Broker failures, timeouts, rate limiting
- Static IP allocation / release / rotation / reuse policy
- Infrastructure lifecycle (instance create/suspend/destroy, auto-renew flags)
- Whitelist JSON/XML fixtures and drift findings
- Fault-injection hooks for Failure Simulator (Part 9)

### 16.5 Dual execution modes

| Mode | How it runs | Providers |
|---|---|---|
| **Local Development Mode** | `docker compose up` | Mock broker + mock infra by default |
| **Production / Real Integration Mode** | Same app image/code; managed Postgres/Redis/Kafka-compatible; Render (or similar) | Real broker adapters + Vultr (or other) via **runtime provider config** (Admin/DB); bootstrap env only for platform wiring |

Switching modes must **not** require changing business logic, routing, services, repositories, or API shapes.

Configuration path (aligned with §14):

1. Compose boots with mock `provider_configs` (or env fallbacks `INFRA_PROVIDER=mock`, `BROKER_PROVIDER=mock`).
2. Optional: Admin Runtime Config activates Vultr/real brokers **without** `.env` edit or restart.
3. Revert to mock the same way for safe demos.

### 16.6 Local failure / chaos testing

| Failure type | How to test locally |
|---|---|
| Redis / Postgres / Redpanda / API down | `docker compose stop <service>` then `start` — **real** dependency outages |
| Process crash + replay | Kill/restart `api` or `worker`; Replay scanner recovers pending orders |
| Broker timeout, DNS, TLS, IP blacklist | **Failure Simulator** on mock providers (Admin UI / API) |
| Concurrent IP rotation races | Two Admin/Swagger rotate calls → distributed lock behavior |

### 16.7 Shared services (same code local and prod)

FastAPI, PostgreSQL access layer, Redis providers, Redpanda/event pipeline, JWT/RBAC, distributed locking, event publishing, monitoring APIs, routing engine, order engine, health scoring, replay engine, Admin UI, Swagger.

Only **deployment targets** and **provider implementations** differ.

### 16.8 Acceptance criteria (Local Lab)

- [ ] `docker compose up --build` starts the full stack with no Vultr/broker secrets required.
- [ ] All 24 assignment parts are demonstrable locally via Admin and/or Swagger using mocks.
- [ ] Mock IP lifecycle and broker flows exercise the same domain services as production providers.
- [ ] `docker compose stop redis` (and similar) produces observable, handled degradation or failure paths.
- [ ] Switching to real Vultr/broker providers is configuration/runtime only — no domain code changes.
- [ ] README documents clone → compose → `/admin` + `/docs` demo path and optional real-provider steps.

---

## 17. User Stories

**US-01** As a client, I place a buy order and receive an accepted/submitted response with order id.  
**US-02** As a client, I cancel an open order and see terminal cancel state.  
**US-03** As an admin, I onboard a new broker account without redeploying routing code.  
**US-04** As an admin, I rotate a broker IP with zero downtime for in-flight orders.  
**US-05** As ops, I view broker health and recent failovers via monitoring APIs.  
**US-06** As ops, I simulate broker timeout and verify automatic failover.  
**US-07** As the system, I refresh broker sessions before expiry without order failures.  
**US-08** As the system, on subscription expiry I block trading and tear down infra per policy.  
**US-09** As the system, after crash I replay pending orders without duplicates.  
**US-10** As an admin, I change routing weights and see immediate effect without restart.  
**US-11** As a tester/admin, I configure my real Vultr API key via Admin API and use real IP orchestration without changing `.env` or restarting.  
**US-12** As a tester/admin, I revert infrastructure provider to mock instantly for safe demos.  
**US-13** As an admin, I validate provider credentials before activation so a bad key cannot break the live provider.  
**US-14** As a reviewer, I open `/admin`, log in, and demonstrate platform modules without using curl.  
**US-15** As a reviewer, I open `/docs` (Swagger) and try any API from the OpenAPI contract.  
**US-16** As an admin, I use the Failure Simulator page to inject faults and observe failover in Monitoring.  
**US-17** As a developer/reviewer, I run `docker compose up` and test all features locally without cloud or broker accounts.  
**US-18** As an operator, I stop Redis/Redpanda via Docker to validate real dependency outage behavior, and use the Simulator for broker/IP fault profiles.  

---

## 18. Use Cases

### UC-01 Place Order (Happy Path)

1. Client authenticates.
2. Client submits buy with `client_order_id`.
3. System validates subscription, schema, capabilities.
4. Router selects broker+IP.
5. Session ensured.
6. Order submitted via provider.
7. Events + audit written.
8. Client receives `SUBMITTED`/`FILLED` as applicable.

### UC-02 Failover on Timeout

1. Primary broker times out (simulated).
2. Attempt marked retryable/failed.
3. Secondary broker selected from chain.
4. Submit once with idempotency safeguards.
5. `failover_total` incremented; `broker.down` may publish.

### UC-03 IP Rotation During Load

1. Orders flowing on IP-A.
2. Admin starts rotation to IP-B.
3. Lock acquired; IP-B prepared; drain IP-A.
4. Cutover; new orders on IP-B; old complete on IP-A.
5. IP-A released per policy.

### UC-04 Whitelist Drift Detected

1. Sync job runs.
2. Assigned IP missing on broker whitelist.
3. Finding `MISSING` recorded; alert/event; optional auto-add.

### UC-05 Subscription Expiry

1. Subscription ends.
2. New orders rejected `SUBSCRIPTION_EXPIRED`.
3. Auto-renewal stopped; infra suspended/destroyed.
4. Audit + `subscription.expired` event.

### UC-06 Hot-Swap Infrastructure Provider (Mock → Vultr)

1. System running with `infrastructure=mock`.
2. Admin calls `PUT /admin/providers/infrastructure` with Vultr API key and `validate_first=true`.
3. Platform probes Vultr; on success encrypts secrets, activates version N+1.
4. ProviderManager rebuilds `VultrProvider` in-process; publishes `provider.activated`.
5. Admin allocates IP — request hits real Vultr.
6. No `.env` change; no process restart.
7. Admin may `PUT` `provider_type=mock` to roll back.

### UC-07 Reject Bad Provider Credentials

1. Admin submits invalid Vultr key with `validate_first=true`.
2. Probe fails; API returns `PROVIDER_VALIDATION_FAILED`.
3. Active provider remains previous (e.g. mock).
4. Audit records failed activation attempt (no secret logged).

### UC-08 Reviewer Demo via Admin UI + Swagger

1. Reviewer opens `/admin`, logs in with demo admin credentials.
2. Uses Dashboard, Brokers, Orders, Static IPs, Runtime Config, Simulator pages.
3. Opens `/docs` from Admin nav and tries an authenticated API call.
4. Confirms assignment modules are demonstrable without curl-only workflows.

### UC-09 Local Lab Cold Start

1. Reviewer clones repo and runs `docker compose up --build`.
2. Stack starts: api, worker, postgres, redis, redpanda (mocks active).
3. Opens `/admin`, logs in, places order, allocates/rotates mock IP, runs failure sim.
4. Opens `/docs` and executes an authenticated API call.
5. No Vultr or real broker credentials were required.

### UC-10 Real Dependency Outage Locally

1. Platform healthy under load/demo traffic.
2. Operator runs `docker compose stop redis`.
3. Lock/session/rate-limit paths degrade or fail closed per policy; errors observable in Admin/logs/metrics.
4. Operator runs `docker compose start redis`; platform recovers.
5. Separately, Failure Simulator injects `BROKER_TIMEOUT` without stopping containers.

---

## 19. Decision Tables

### 19.1 Routing Candidate Eligibility

| Condition | Eligible? |
|---|---|
| Broker disabled | No |
| Subscription expired | No |
| Capability missing | No |
| Health UNHEALTHY | No (unless override) |
| No IP and cannot allocate | No |
| Rate limit exceeded + policy REJECT | No |
| Rate limit exceeded + policy REROUTE | Skip this broker |
| Rate limit exceeded + policy QUEUE | Yes (queued) |
| Session unrecoverable | No |

### 19.2 IP Reuse Policy

| Policy | Behavior |
|---|---|
| `NEVER_SAME_BROKER_UNTIL_RELEASE` | Default assignment rule BR-G04 |
| `COOLDOWN_HOURS=N` | After release, wait N hours before same broker reuse |
| `ALLOW_SHARE_CROSS_BROKER` | Same IP may attach to different brokers (BR-G03) |

### 19.3 Rotation Timeout Policy

| Policy | On drain timeout |
|---|---|
| `ABORT_ROTATION` | Keep old IP; release new if unused |
| `FORCE_CUTOVER` | Switch; remaining old orders finish or fail per order policy |

### 19.4 Expiry Teardown Policy

| Mode | Action |
|---|---|
| `SUSPEND` | Stop instances; keep IPs reserved optional |
| `DESTROY` | Destroy instances + release IPs |

### 19.5 Provider Activation

| Condition | Result |
|---|---|
| `validate_first=true` and probe fails | Reject; keep previous active provider |
| `validate_first=true` and probe succeeds | Encrypt, activate, rebuild provider, audit |
| `validate_first=false` | Activate immediately (discouraged in prod) |
| Rollback requested | Restore previous version; rebuild provider |
| GET provider config | Secrets masked |

---

## 20. Edge Cases & Failure Scenarios

| Scenario | Expected Behavior |
|---|---|
| Duplicate `client_order_id` | Return original order; no second submit |
| Broker timeout | Retry/failover per policy |
| Broker ack lost (indoubt) | Reconcile via status query; no blind resubmit |
| IP rotation during execution | In-flight bound to old IP until complete; new orders post-cutover use new IP |
| Redis down | Degrade per policy: fail closed on locks for rotation; orders may use fallback single-instance lock only in dev—not prod |
| Redpanda down | Buffer/fallback MemoryEventProvider or durable outbox retry |
| Vultr API down | Infra ops fail gracefully; trading continues if IP already attached |
| Whitelist lag after rotate | Gate cutover on sync OK or timeout policy |
| Concurrent allocate same IP | DB constraints + locks prevent conflict |
| Subscription expires mid-order | Allow in-flight completion policy configurable; block new |
| Credential decrypt failure | Fail session; broker marked session_error; alert |
| Queue saturation | `503 QUEUE_FULL` / backpressure response |
| Partial fill then failover | Do not open duplicate exposure; cancel/reconcile path |
| Bad Vultr key on activate | `PROVIDER_VALIDATION_FAILED`; previous provider stays active |
| Runtime config missing after boot | Fall back to safe defaults (mock) + warn metric |
| Mid-flight provider swap during IP op | In-flight op finishes on provider instance captured at start; new ops use new provider |

---

## 21. Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-1 | Performance | p95 order accept latency < 200ms under nominal load (mock path) |
| NFR-2 | Throughput | Demonstrate ~5k orders/min |
| NFR-3 | Scalability | Stateless API; horizontal scale design for 100k+/min |
| NFR-4 | Availability | Design for multi-instance API; no in-memory-only prod state |
| NFR-5 | Reliability | Idempotent submits; replay-safe recovery |
| NFR-6 | Security | AuthN/Z, encryption, HMAC optional, audit |
| NFR-7 | Maintainability | Provider architecture; clean modules |
| NFR-8 | Observability | Metrics, JSON logs, monitoring APIs |
| NFR-9 | Portability | Docker Compose dev; Render prod path |
| NFR-10 | Testability | Unit/integration/concurrency/failover/provider-switch tests |
| NFR-11 | Operability | Integration providers/credentials hot-configurable without env edit or restart |
| NFR-12 | Demonstrability | `/admin` HTML ops UI + `/docs` Swagger available on the same FastAPI service |
| NFR-13 | Local Lab | Full stack via Docker Compose with mocks; zero required external cloud/broker accounts for assignment demos |

---

## 22. Security & Compliance Requirements

1. Least-privilege RBAC on admin/infra/monitoring mutations.
2. Encrypt broker credentials, Vultr tokens, and refresh tokens at rest.
3. Rotate JWT signing keys and API keys with overlap window.
4. HMAC for high-risk routes when enabled.
5. Audit logs immutable (append-only table; no update/delete API).
6. PII/secrets scrubbing in logs; provider GET responses mask secrets.
7. Network: TLS in production; bootstrap secrets via env/secret manager—not git.
8. Runtime provider config changes restricted to `admin` role; test/probe may allow `ops`.

---

## 23. Observability Requirements

- Prometheus `/metrics`
- Structured JSON logs to stdout
- Correlation ids on all requests
- Domain events for async pipelines
- Monitoring REST APIs (FR-23)
- Health endpoints: liveness/readiness
- Metrics for provider activations: `provider_activate_total{kind,type,result}`

---

## 24. Acceptance Criteria (Release Gate)

The release is acceptable for assignment submission when:

1. All FR-01…FR-24 are demonstrable (code + docs + tests/logs as applicable).
2. Buy/Sell/Cancel/Status/History APIs work end-to-end on mock providers.
3. IP allocate/rotate/release + whitelist sync + audit trail verified.
4. Distributed lock prevents concurrent rotation races.
5. Failover + replay demos show no duplicate submits.
6. Subscription expiry blocks trading and triggers infra policy.
7. Providers switch via **runtime configuration** (Admin API / DB), not only env files.
8. Demo path: mock → Vultr (with tester-supplied key) → mock **without** `.env` edit or process restart.
9. Docker Compose brings up API + worker + Postgres + Redis + Redpanda with **mock providers by default** (no cloud/broker secrets required).
10. PRD + TDD + README + diagrams exist and match implementation.
11. Scalability narrative (FR-24) documented in TDD.
12. **Operations Admin UI** available at `/admin` (FastAPI-hosted HTML) covering module demos per §15.
13. **Swagger UI** available at `/docs` (plus `/redoc`, `/openapi.json`) for full API try-it-out.
14. Admin UI links to Swagger; each assignment part has an Admin and/or Swagger demo path.
15. **Local Lab (§16):** all 24 parts demonstrable via `docker compose up`; dependency outages testable via `docker compose stop/start`; broker/IP faults via Failure Simulator; real providers optional via runtime config only.

---

## 25. Risks, Assumptions, Dependencies

### Risks

| Risk | Mitigation |
|---|---|
| Vultr API changes / rate limits | Adapter isolation; mock for CI |
| Exactly-once across brokers is hard | Idempotency + indoubt reconciliation; document guarantees carefully |
| Whitelist propagation delay | Cutover gates; timeout policies |
| Scope creep to 24 isolated features | Dependency-ordered implementation; shared kernel |
| Redis/Redpanda outage | Explicit degradation modes; outbox pattern |
| Hot-swap with bad credentials | Validate-then-activate; versioned rollback |
| Secret leakage via admin GET | Mandatory redaction + audit of reads if needed |

### Assumptions

- Assignment evaluation accepts mock providers for brokers/Vultr in CI and local lab.
- “Unlimited brokers” means data/config scalability, not infinite adapter implementations in v1.
- Render (or equivalent) hosts API; managed Postgres/Redis; Kafka-compatible bus available or documented.
- Reviewers may supply their own Vultr/broker credentials via Admin API for live verification (**optional**).
- True public static IPs are not available from Docker alone; mock infra simulates lifecycle locally.

### Dependencies

- PostgreSQL, Redis, Redpanda (or compatible), Docker, Python 3.12 ecosystem.
- Vultr account for real infra provider testing (optional for core grade if mock complete).
- Bootstrap `SECRETS_FERNET_KEY` available so runtime secrets can be encrypted.

---

## 26. Deliverables

| Deliverable | Description |
|---|---|
| Source code | Modular monolith per TDD |
| PRD.md | This document |
| TDD.md | Technical design |
| README | Runbook: setup, demo scripts, env, `/admin` + `/docs` URLs |
| ERD | Database entity relationship diagram |
| Sequence diagrams | Order, rotation, failover, replay, provider hot-swap |
| OpenAPI / Swagger | FastAPI `/docs`, `/redoc`, `/openapi.json` |
| Operations Admin HTML | FastAPI-served `/admin` UI (sample HTML UX baseline) |
| Docker Compose | Local lab stack (api, worker, postgres, redis, redpanda) |
| Local Lab runbook | README: clone → compose → `/admin` + `/docs`; chaos via compose stop + simulator |
| Deployment guide | Render production path |
| Tests | pytest suite including provider hot-swap |
| Metrics | Prometheus endpoint |

---

## 27. Glossary

| Term | Meaning |
|---|---|
| BrokerBridge | Working product name for the gateway |
| Provider | Swappable adapter behind an interface |
| Bootstrap config | Env/secret-manager settings required to start the process |
| Runtime config | DB/Admin settings applied live without restart |
| Provider hot-swap | Rebuilding a provider instance in-process after config change |
| Validate-then-activate | Probe credentials before making a provider active |
| Operations Admin UI | FastAPI-hosted HTML ops console at `/admin` |
| Swagger / OpenAPI | Interactive API docs at `/docs` (FastAPI built-in) |
| Local Development Lab | Full `docker compose` environment with mocks for offline E2E demos |
| Dual execution mode | Local (mocks) vs production/real providers; same app code |
| Documentation IP range | TEST-NET addresses used by MockInfrastructureProvider (not real public Vultr IPs) |
| Static IP | Durable public egress IP used for broker whitelisting |
| Cutover | Moment routing switches from old IP to new IP |
| Drain | Period waiting for in-flight work on old IP |
| Idempotency key | Client-supplied unique order identity |
| Indoubt | Submission result unknown; needs reconciliation |
| Soft failover | Switch brokers without confirming prior submit |
| Weighted routing | Score-based broker selection |
| Modular monolith | Single deployable with modular boundaries |

---

## Appendix A — Requirement Traceability Matrix

| Assignment Part | FR | Primary Modules (logical) |
|---|---|---|
| 1 | FR-01 | routing, health, orders |
| 2 | FR-02 | ip_manager, infrastructure |
| 3 | FR-03 | ip_manager, broker |
| 4 | FR-04 | ip_manager, locks, orders |
| 5 | FR-05 | health, monitoring |
| 6 | FR-06 | orders, workers |
| 7 | FR-07 | providers/lock |
| 8 | FR-08 | infrastructure, subscriptions |
| 9 | FR-09 | failure simulation, mock providers |
| 10 | FR-10 | monitoring |
| 11 | FR-11 | events |
| 12 | FR-12 | auth, security |
| 13 | FR-13 | docs, `/docs` Swagger, `/admin` UI |
| 14 | FR-14 | broker |
| 15 | FR-15 | broker, routing |
| 16 | FR-16 | routing |
| 17 | FR-17 | sessions |
| 18 | FR-18 | rate limit, routing |
| 19 | FR-19 | orders, routing |
| 20 | FR-20 | ip_manager |
| 21 | FR-21 | config, providers, admin provider APIs |
| 22 | FR-22 | orders, workers |
| 23 | FR-23 | monitoring APIs |
| 24 | FR-24 | TDD scalability |

---

## Appendix B — Sample Business Payloads

### Place Buy (logical)

```json
{
  "client_order_id": "c-10001",
  "side": "BUY",
  "symbol": "AAPL",
  "quantity": 10,
  "order_type": "MARKET",
  "time_in_force": "DAY",
  "preferred_broker_id": null,
  "region_preference": "ewr"
}
```

### IP Rotate Request (logical)

```json
{
  "broker_account_id": "brk_123",
  "target_region": "ewr",
  "drain_timeout_seconds": 30,
  "on_timeout": "ABORT_ROTATION"
}
```

### Whitelist Sync Finding (logical)

```json
{
  "broker_account_id": "brk_123",
  "assigned_ip": "45.76.1.10",
  "status": "MISSING",
  "source_format": "XML",
  "detected_at": "2026-07-23T12:00:00Z"
}
```

### Activate Vultr Infrastructure Provider (logical)

```json
{
  "provider_type": "vultr",
  "scope": "global",
  "validate_first": true,
  "activate": true,
  "config": {
    "api_key": "vultr-xxxxx",
    "default_region": "ewr"
  }
}
```

### Activate Response (secrets redacted)

```json
{
  "kind": "infrastructure",
  "provider_type": "vultr",
  "version": 3,
  "status": "active",
  "config": {
    "api_key": "***",
    "default_region": "ewr"
  },
  "validated": true,
  "activated_at": "2026-07-23T15:30:00Z"
}
```

### Revert to Mock Infrastructure (logical)

```json
{
  "provider_type": "mock",
  "activate": true,
  "validate_first": false
}
```

---

## Document Control

| Version | Date | Notes |
|---|---|---|
| 0.1 | — | Early drafts (superseded) |
| 1.0 | — | Outline drafts (superseded) |
| 2.0 | 2026-07-23 | Full implementation-ready PRD replacing all prior drafts |
| 2.1 | 2026-07-23 | Runtime provider configuration: no-env / no-restart hot-swap for Vultr & integrations |
| 2.2 | 2026-07-23 | FastAPI-hosted Operations Admin HTML + Swagger/OpenAPI; full module demo coverage |
| 2.3 | 2026-07-23 | Local Development Lab & dual execution modes (Compose + mocks; real providers optional) |

**End of PRD**
