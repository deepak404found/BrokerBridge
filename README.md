# BrokerBridge

Production-oriented **Broker Network Gateway & Static IP Orchestrator** (working name).

## Specs & plans

- Product: [`local/PRD.md`](local/PRD.md)
- Technical: [`local/TDD.md`](local/TDD.md)
- Master plan: [`docs/plans/2026-07-23-master-implementation-plan.md`](docs/plans/2026-07-23-master-implementation-plan.md)
- Agent guide: [`CLAUDE.md`](CLAUDE.md)
- Changelog: [`CHANGELOG.md`](CHANGELOG.md)

## Status

Documentation and planning complete (PRD/TDD v2.3, waves W0–W6).  
**Next:** execute Wave 0 (Local Lab foundation) — see `docs/plans/2026-07-23-wave-0-foundation.md`.

## Target Local Lab (after Wave 0+)

```bash
docker compose up --build
```

| Surface | URL |
|---|---|
| Admin | http://localhost:8000/admin |
| Swagger | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |

## Wave workflow

1. Implement wave plan → test  
2. Ask before commit  
3. On approval: commit + update `CHANGELOG.md` + `docs/changelogs/WAVE-XX.md`
