# Changelog

All notable changes to BrokerBridge are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/).  
Per-wave detail: `docs/changelogs/WAVE-XX.md`.  
Commit + changelog updates happen **after wave testing**, only with user approval (see `.cursor/rules/wave-changelog-commits.mdc`).

## [Unreleased]

### Documentation

- Planning artifacts continue under `docs/plans/` for upcoming waves

## [0.5.0] - 2026-07-24

### Added

- Zero-downtime IP rotation (`POST …/rotate-ip`) with drain/cutover and abort-on-timeout default
- Multi-region allocation polish and region-aware infrastructure paths
- Transactional outbox + worker drain to dual-mode EventProvider (Memory / Redpanda local / Kafka-shaped)
- Event envelope publish on order, IP, and config mutations; monitoring list + drain APIs
- Admin Event Bus with WebSocket live refresh (`/api/v1/ws/events`) and Runtime Config for kind=`event`
- Cloud Kafka SSL/SASL wiring fixes for day-2 bus swap without restart
- Alembic `004_w4` outbox table; `.env.example` event-bus placeholders (no secrets)
- Pytest coverage for rotation, outbox, events, regions, WS, provider reload, OpenAPI W4 paths
- Compose E2E helper `scripts/w4_compose_e2e.sh`

### Who / Where

- Who: deepak404found
- Where: branch `main`

See `docs/changelogs/WAVE-04.md` for detail.


## [0.4.0] - 2026-07-24

### Added

- Broker health scoring + probe APIs and Admin Broker Health page
- Per-broker rate-limit snapshots (Redis in Compose / Memory in pytest) and Admin Rate Limits page
- Smart routing (`WEIGHTED_SCORE`) with `require_assigned_ip=true`, config weights GET/PUT, and routing preview
- Inline Mode B orders: buy/sell/cancel/history with idempotency and basic failover
- Alembic `003_w3` models for orders, attempts, health snapshots, failover events
- Admin Orders UX: field labels and auto-filled editable `client_order_id`
- Compose loads secrets via `env_file: .env`; `.env.example` documents Local Lab placeholders
- Pytest coverage for health, rate limits, routing, orders, failover, OpenAPI W3 paths
- Compose E2E helper `scripts/w3_compose_e2e.sh`

### Who / Where

- Who: deepak404found
- Where: branch `main`

See `docs/changelogs/WAVE-03.md` for detail.

## [0.3.0] - 2026-07-24

### Added

- Broker account CRUD, ensure/destroy sessions under Redis locks, and monitoring session list APIs
- Static IP / instance lifecycle (allocate, assign, release) with BR-G04 reuse cooldown and whitelist sync
- Alembic `002_w2` models for brokers, sessions, infrastructure, IP history, whitelist, and config items
- Expanded mock broker/infra providers plus Redis lock and session adapters
- Admin wiring for Brokers, Sessions, Static IPs, and Whitelist (`js/w2.js`) with login gate
- Static IPs UX: display_name labels, status-aware actions/icons, clearer unique-IP and cooldown messaging
- Seeded Demo Lab Client, Mock Alpha/Beta brokers, and `ip.reuse.cooldown_hours`
- Pytest coverage for brokers, sessions, IP manager, locks, whitelist, and OpenAPI W2 paths
- Compose E2E helper `scripts/w2_compose_e2e.sh`

### Who / Where

- Who: deepak404found
- Where: branch `main`

See `docs/changelogs/WAVE-02.md` for full Wave 2 detail.

## [0.2.0] - 2026-07-24

### Added

- Async DB layer (SQLAlchemy 2 + Alembic) with `Client`, `User`, and `ProviderConfig` models
- Provider framework: protocols, mock broker/infrastructure adapters, `ProviderManager` (DB → env → mock)
- Fernet-encrypted provider secrets; admin provider list/get/put APIs with masked secrets
- JWT auth: bcrypt passwords, `POST /api/v1/auth/token`, role-gated admin routes
- Seeded admin user + default mock provider configs; Admin UI login wiring in `api.js`
- OpenAPI examples and documented 401 responses for protected admin endpoints
- Tests for auth, providers, and DB models (20 total)

### Who / Where

- Who: deepak404found
- Where: branch `main` @180fb64

See `docs/changelogs/WAVE-01.md` for full Wave 1 detail.

## [0.1.0] - 2026-07-23

### Added

- Local Lab via Docker Compose (api, worker, postgres, redis, redpanda)
- Poetry project (`pyproject.toml` + `poetry.lock`)
- FastAPI health endpoints with typed live/ready schemas and TCP readiness probes
- Centralized API error envelope and `X-Request-ID` middleware
- Operations Admin HTML shell at `/admin` and Swagger at `/docs`
- Worker heartbeat stub and pytest suite (10 tests)

### Who / Where

- Who: deepak404found
- Where: branch `main` @c2d8a5e

See `docs/changelogs/WAVE-00.md` for full Wave 0 detail.
