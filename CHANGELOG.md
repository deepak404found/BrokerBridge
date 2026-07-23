# Changelog

All notable changes to BrokerBridge are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/).  
Per-wave detail: `docs/changelogs/WAVE-XX.md`.  
Commit + changelog updates happen **after wave testing**, only with user approval (see `.cursor/rules/wave-changelog-commits.mdc`).

## [Unreleased]

### Documentation

- Planning artifacts continue under `docs/plans/` for upcoming waves

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
