# Wave 1 — Data + Providers + Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Checkbox steps for tracking.

**Goal:** Persist core entities in Postgres, introduce the provider framework (memory + mock infra/broker stubs + `provider_configs`), and ship JWT login + RBAC so Admin/Swagger can authenticate.

**Architecture:** SQLAlchemy 2 async + Alembic; `ProviderManager` resolves ports from DB config with env fallback; FastAPI deps enforce JWT/`admin` role. Domain still does not import Redis/Vultr/broker SDKs.

**Tech Stack:** Poetry, SQLAlchemy 2 + asyncpg, Alembic, PyJWT, bcrypt, cryptography (Fernet), existing FastAPI stack.

## Global Constraints

- Specs: `local/TDD.md` §4–5, §11, §13.1, §20; PRD FR-12, FR-21 foundation.
- Poetry only; never commit `local/` or `.env`.
- Ask before commit at wave end; update `CHANGELOG.md` + `docs/changelogs/WAVE-01.md`.
- Keep W0 health/error contracts working.

## Out of Scope (W1)

- Full broker/IP/order domain APIs (W2+)
- Vultr real HTTP calls (mock infra only)
- Redpanda producers, Redis lock/cache adapters (stubs/protocols OK; Redis provider can be thin or deferred to W2)
- Zero-downtime rotation, failover, replay

---

## File map

```text
app/
  db/
    base.py, session.py, seed.py
  models/
    client.py, user.py, provider_config.py
  providers/
    base.py, manager.py, memory.py
    broker/mock.py
    infrastructure/mock.py
  auth/
    passwords.py, jwt.py, deps.py
  api/routes/
    auth.py, admin_providers.py
  schemas/
    auth.py, providers.py
migrations/
tests/
  test_auth.py, test_providers.py, test_db_models.py
```

---

### Task 1: Dependencies + settings

- [x] Add Poetry deps: sqlalchemy[asyncio], asyncpg, alembic, pyjwt, bcrypt, cryptography, email-validator, python-multipart, aiosqlite
- [x] Settings: jwt_*, secrets_fernet_key, seed admin, infra/broker provider defaults
- [x] `.env.example` updated

### Task 2: DB session + Alembic + core models

- [x] Async engine/session factory from `DATABASE_URL`
- [x] Models: `Client`, `User` (role enum), `ProviderConfig`
- [x] Alembic migration initial (`001_initial`)
- [x] Startup `create_all` + seed; Alembic documented in README
- [x] Tests use sqlite+aiosqlite

### Task 3: Provider framework

- [x] Protocols + MockBroker, MockInfrastructure, Memory*
- [x] `ProviderManager` resolution: DB → env → mock
- [x] Seed active global infrastructure/broker mock configs
- [x] Tests for resolution

### Task 4: Admin provider APIs (2b)

- [x] `GET /api/v1/admin/providers`, `GET/PUT /api/v1/admin/providers/{kind}`
- [x] validate_first + activate + masked secrets on GET
- [x] Fernet encrypt secrets at rest
- [x] Tests for activate mock and validation failure

### Task 5: Auth JWT + RBAC

- [x] `POST /api/v1/auth/token` (OAuth2 form; username = email)
- [x] Password hashing (bcrypt); JWT create/decode
- [x] Deps: `get_current_user`, `require_roles`
- [x] Protect admin provider routes
- [x] Seed admin on startup
- [x] Admin JWT login panel in `js/api.js`
- [x] Tests: login success/fail; protected route 401

### Task 6: Verification

- [x] `poetry run pytest -q` (20 passed)
- [ ] Compose smoke (login → admin providers) — optional before commit
- [x] Ask user to commit + changelog

## Definition of Done

- [x] Alembic migration present for Local Lab Postgres
- [x] JWT login works (tests + Swagger path)
- [x] ProviderManager returns mock infra/broker
- [x] Admin provider GET/PUT works with auth; secrets masked
- [x] Tests pass; user offered commit; committed + changelog
