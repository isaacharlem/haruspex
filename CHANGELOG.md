# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-06-09

### Added

- API service: API-key auth (hashed at rest, three scopes), idempotent batched
  ingest, run lifecycle (register/heartbeat/kill/ack/complete), LTTB metric
  series, SSE event stream over Postgres LISTEN/NOTIFY, policies CRUD with
  dry-run replay, cost ledger, calibration transparency endpoints.
- Forecaster: pow3/exp3/linlog + martingale model averaging with parametric
  bootstrap, divergence head with grad-norm precursor features, per-outcome
  isotonic calibration, seeded behavioral test suite.
- Policy worker: 15s refit/evaluate loop with hysteresis, checkpoint guard,
  grace + ack-timeout handling, retrospective forecast trajectories,
  calibration refits.
- Python SDK (`haruspex`): non-blocking instrumented runs with batching,
  heartbeats, ring-buffer resilience, kill-directive handling, Lightning and
  HF Trainer callbacks, and the `haruspex-simulate` synthetic-run generator
  (stream + backfill).
- Dashboard: fleet, run detail with prognosis fan, policy editor with dry-run
  drawer, calibration page, honest two-number ledger, key management, and the
  Analyst (Anthropic-powered copilot with server-side tools).
- Packaging: multi-stage Docker images (api, worker, frontend), compose stack
  with a one-shot demo profile, full CI (lint, types, tests with coverage
  gates, placeholder audit, gitleaks, contract, integration smoke, Playwright
  e2e), build-only release pipeline.
