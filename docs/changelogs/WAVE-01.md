# Wave Changelog — WAVE-01

## Metadata

| Field | Value |
|---|---|
| **Wave** | W1 |
| **Title** | Data + Providers + Auth |
| **Plan** | `docs/plans/WAVE-1-data-providers-auth.md` |
| **Status** | completed |
| **When** | 2026-07-24 |
| **Who** | deepak404found \<deepakyadu404@gmail.com\> |
| **Where** | branch `main` `180fb64` |
| **Why** | Unlock Local Lab persistence, pluggable mock/real providers, and JWT-protected admin APIs so later waves can build sessions, IPs, and orders on a real auth + config foundation |

## What changed

### Features / behavior

- Async SQLAlchemy 2 session + Postgres URL; tests on sqlite+aiosqlite
- Core models: `Client`, `User` (roles), `ProviderConfig`
- Alembic wiring (`alembic.ini`, `migrations/`) with initial schema path for Local Lab
- Startup `create_all` + seed admin user and default mock provider configs
- Provider protocols + `MockBroker` / `MockInfrastructure` + in-memory stores
- `ProviderManager` resolves active config: DB → env defaults → mock
- Fernet encryption for provider secrets at rest; masked secrets on GET
- JWT auth (bcrypt passwords, OAuth2 form token endpoint, role deps)
- Admin UI JWT login helper in `app/static/admin/js/api.js`
- OpenAPI examples / richer error + health schemas for Swagger demos

### APIs / Admin / Swagger

- `POST /api/v1/auth/token` — OAuth2 password form (username = email)
- `GET /api/v1/admin/providers` — list provider configs (auth required)
- `GET/PUT /api/v1/admin/providers/{kind}` — read/activate with validate-first
- Protected admin routes return 401 without bearer token (documented in OpenAPI)
- `/docs` and `/admin` remain enabled

### Files (high level)

- Created: `app/db/**`, `app/models/**`, `app/providers/**`, `app/auth/**`, `app/api/routes/auth.py`, `app/api/routes/admin_providers.py`, `app/api/openapi.py`, `app/schemas/auth.py`, `app/schemas/providers.py`, `app/core/crypto.py`, `alembic.ini`, `migrations/**`, `tests/test_auth.py`, `tests/test_providers.py`, `tests/test_db_models.py`, `docs/plans/WAVE-1-data-providers-auth.md`
- Modified: settings, main/router, health/error schemas, docker-compose, `.env.example`, README, `pyproject.toml` / lockfile, admin `api.js`, conftest + existing tests, master plan

### Tests

- Commands run: `poetry run pytest -q`
- Results: **20 passed** (1 Starlette/httpx deprecation warning)

### How verified (Local Lab)

- [x] `poetry run pytest -q` (20 passed)
- [ ] Compose smoke (login → admin providers) — optional; deferred if not run this session
- [x] Swagger paths present for auth + admin providers (OpenAPI in tree)
- [x] Provider manager + auth covered by unit/API tests

## Notes / follow-ups

- Out of scope deferred to W2: brokers/sessions, static IP lifecycle, locks, whitelist
- Compose UI smoke remains optional checklist item if not exercised before this commit
