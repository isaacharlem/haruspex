# Haruspex

**Haruspex watches your live training runs, forecasts each one's fate with calibrated probabilities, kills the doomed ones under policy, and tells you — in dollars — what it saved.**

[![ci](https://github.com/isaacmharlem/haruspex/actions/workflows/ci.yml/badge.svg)](https://github.com/isaacmharlem/haruspex/actions/workflows/ci.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-8A6F3F.svg)](LICENSE)
[![python 3.12](https://img.shields.io/badge/python-3.12-4E8F7B.svg)](https://www.python.org/downloads/release/python-3120/)

## The problem

A meaningful fraction of expensive training runs were never going to work, and most teams find out at the end. Görmez & Yorulmaz ([arXiv:2405.18710](https://arxiv.org/abs/2405.18710)) measured that roughly one in ten LLM pretraining runs with *identical configurations* diverged on the random seed alone — failures nobody could have configured away, burning their full GPU budget unless someone was watching the loss curve at 3am. Add the runs that plateau short of target, and the wasted-compute share of a training budget gets uncomfortable.

The classic answer — ASHA/Hyperband-style early stopping — only works *inside* a hyperparameter sweep: it prunes a trial because sibling trials with the same budget are doing better. A lone pretraining run, a finetune, the one big run that matters most, has no siblings to compare against. Pruning it requires a forecast of its own future, not a leaderboard — which is exactly the part ASHA never had.

## What Haruspex does

- **Forecast** — every 15 s it refits learning-curve models per run and produces calibrated `P(hit target)`, `P(diverge)`, `P(plateau)` with a final-metric quantile fan.
- **Police** — declarative kill policies with hysteresis, a checkpoint guard, a grace window, and a human override; every fire carries its forecast snapshot.
- **Account** — each kill books *gross freed compute* and *forecast-weighted expected value*, in dollars, never collapsed into one inflated number.
- **Explain** — an embedded AI analyst answers "why was run 44 killed?" from the same data the dashboard shows.

## The 90-second demo

```bash
git clone https://github.com/isaacmharlem/haruspex && cd haruspex
cp .env.example .env
make demo
```

`make demo` builds the images, boots Postgres + API + worker + dashboard, prints a dashboard key, then seeds 40 completed historical runs and starts 8 live simulated ones. Open **http://localhost:8080**, paste the key, and watch:

- **t+0:30** — first forecasts land; prognosis fans appear on the live traces.
- **t+1:00** — a divergent run's grad norm starts climbing; its card flips to AT_RISK. The calibration page is already fitted from the 40-run backfill.
- **t+2–3:00** — `P(diverge)` sustains above the default policy's threshold for three evaluations; the kill fires (respecting grace and the checkpoint guard), the trainer acknowledges, the card shows the KILLED sigil, and gross/expected dollars land on the ledger.
- **t+5:00** — healthy runs complete; the `spiky_recoverer` run — whose loss spiked twice and recovered — is still alive, because forecasting beats flinching.

The simulator is a shipping feature, not a fixture: it drives the same public SDK and API as a real training job.

![The fleet mid-demo: live runs with prognosis fans, two killed divergents, the spiky recoverer alive](docs/fleet.png)

![Run detail: the trace instrument, prognosis numerals, forecast components, calibration badge](docs/run-detail.png)

## Architecture

```mermaid
flowchart LR
    T[training job + SDK] -- "batched ingest + 5s heartbeat" --> A[api FastAPI]
    A -- "kill directive on heartbeat" --> T
    A -- writes --> P[(Postgres 16)]
    W[worker refit and policies] -- "reads + writes" --> P
    P -- "LISTEN/NOTIFY" --> H[SSE hub in api]
    H -- "run / forecast / policy / ledger events" --> B[browser dashboard]
    B -- "REST + copilot chat SSE" --> A
    A -- "Messages API + tools" --> C[Anthropic API]
```

One Postgres holds everything. The stateless **api** service handles ingest, CRUD, auth, the SSE fan-out, and proxies the Analyst (the Anthropic key never reaches the browser). The **worker** — same codebase, separate process — refits forecasts every 15 s per active run, evaluates policies, maintains liveness, backfills retrospective forecast trajectories for imported history, and refits the calibration layer as labeled runs accumulate. Postgres `LISTEN/NOTIFY` carries change events to each api replica's in-process SSE hub, so two browser tabs update live with no polling anywhere.

## Instrument your training

```bash
uv pip install -e sdk   # from this repo; the release pipeline builds the wheel,
                        # and PyPI publishing activates when a PYPI_API_TOKEN is configured
```

The vanilla loop:

```python
import haruspex

run = haruspex.init(
    name="gpt2-small-bf16", tags=["pretrain"],
    target=("loss", 2.9, "min"),
    budget_steps=10_000, budget_wallclock_s=4 * 3600,
    gpu=("H100", 8),
)
for step in range(10_000):
    loss, grad_norm, lr = train_step()
    run.log(step=step, loss=loss, grad_norm=grad_norm, lr=lr)
    if run.should_stop():          # set by a Haruspex kill directive
        save_checkpoint()
        break
run.finish(status="completed", final={"loss": loss})
```

The SDK never blocks or raises into your training loop: a background thread batches points (500 points or 2 s), heartbeats every 5 s, ring-buffers up to 50k points across outages (drop-oldest), and retries with jittered backoff under stable idempotency keys. If a kill directive arrives, `run.should_stop()` flips, your `on_kill` hook fires once, and `run.finish()` acknowledges the kill. Configure via arguments or `HARUSPEX_API_URL` / `HARUSPEX_API_KEY`.

**PyTorch Lightning** — sets `trainer.should_stop` on a kill directive:

```python
import haruspex
from haruspex.callbacks.lightning import HaruspexCallback

run = haruspex.init(
    name="vit-b16", tags=["finetune"],
    target=("loss", 0.4, "min"),
    budget_steps=5_000, budget_wallclock_s=2 * 3600,
    gpu=("A100", 4),
)
trainer = L.Trainer(max_steps=5_000, callbacks=[HaruspexCallback(run)])
trainer.fit(model, datamodule)
```

**Hugging Face Trainer** — sets `control.should_training_stop`:

```python
import haruspex
from haruspex.callbacks.transformers import HaruspexCallback

run = haruspex.init(
    name="bert-mlm", tags=["pretrain"],
    target=("loss", 1.8, "min"),
    budget_steps=20_000, budget_wallclock_s=8 * 3600,
    gpu=("L40S", 2),
)
trainer = Trainer(model=model, args=args, train_dataset=ds,
                  callbacks=[HaruspexCallback(run)])
trainer.train()
```

Both callbacks log the loss and learning rate, report checkpoint saves (which feeds the kill policy's checkpoint guard), and finish the run when training ends. The framework imports are guarded: the SDK installs with only `httpx` and `numpy`.

## The forecaster

Each refit fits three curve families to the raw target-metric series — `pow3: c + a·t^(−b)`, `exp3: c + a·e^(−b·t)`, and `lin-log: c + a·ln(t) + b·t` — with robust (`soft_l1`) least squares, plus a last-value martingale baseline that wins whenever the parametric families don't actually explain the data. The families are model-averaged with weights ∝ `exp(−AIC/2)`, and a 500-draw parametric bootstrap (moving-block residual resampling with covariance-seeded refits) yields the final-metric quantiles and `P(hit target)`. A separate divergence head watches the raw series for the failure signature: a z-scored rise in Δgrad-norm (the precursor that fires *before* the loss moves), current loss elevation over its trailing floor, sustained growth, NaN/Inf, and the lr×grad-norm interaction, blended logistically — with fixed documented weights until ≥30 labeled runs allow an org-wide logistic refit. `P(plateau)` is the renormalized remainder.

The calibration story is honest: probabilities are isotonic-calibrated per outcome against *your own completed runs* (forecasts at 25/50/75 % progress vs. what actually happened), the dashboard shows you the reliability diagram and Brier score before/after, and every forecast is explicitly badged **calibrating** until at least 30 labeled runs exist — until then you get raw model output clipped to [0.05, 0.95], and the Analyst caveats every probability it quotes.

## Policies

A policy is a small JSON document, validated on write (unknown fields rejected):

```json
{
  "name": "kill-doomed-after-warmup",
  "scope": { "tags": ["pretrain"] },
  "when": {
    "signal": "p_hit_target",
    "op": "<",
    "value": 0.05,
    "after_progress": 0.10,
    "sustained_evals": 3
  },
  "action": {
    "type": "kill",
    "grace_seconds": 120,
    "min_checkpoint_age_seconds": 600,
    "notify": true
  }
}
```

Signals: `p_hit_target`, `p_diverge`, `p_plateau`, `progress`, or `metric:<name>`. The worker evaluates every enabled policy after each forecast refit; a rule must trip `sustained_evals` times consecutively before firing (hysteresis — one bad refit never kills a run). Firing sets the run's kill directive and writes a `KILL_ISSUED` event with the full forecast snapshot. The SDK sees the directive on its next heartbeat, runs your checkpoint hook, stops the trainer, and acknowledges — at which point the dollars are booked. If no acknowledgment arrives within `grace_seconds + 60`, the worker marks the run `LOST` and notes the timeout on the event. The **checkpoint guard** (`min_checkpoint_age_seconds`) defers a kill until the trainer has a fresh-enough checkpoint, and records how long it waited. An admin can override any pending kill within the grace window (`POST /v1/runs/{id}/kill` with `{"cancel": true}`), which writes an `OVERRIDDEN` event.

Before enabling a rule, **dry-run** it: `POST /v1/policies/dry-run` (or the drawer in the policy editor) replays the candidate over your historical forecast trajectories and returns exactly which runs would have fired, where, and the estimated gross/expected dollars — with its assumptions stated.

## The Analyst

A dockable chat panel that talks through the dashboard. Questions it answers well:

- *"Which runs are at risk right now and why?"* — lists runs with `P(diverge)` and the divergence features driving them.
- *"Explain why run 44 was killed."* — reconstructs the causal chain from the policy's fire-time snapshot: what the forecast said, which rule tripped, and what actually happened.
- *"What did the kill policy save us this week, and should I trust that number?"* — quotes both ledger numbers and checks the calibration page before vouching for the expected-value figure.

Enable it by setting `ANTHROPIC_API_KEY` in `.env` and restarting (`HARUSPEX_COPILOT_MODEL` overrides the default `claude-sonnet-4-6`). Tools execute server-side against the same service layer as the REST API; the model gets eight read-only tools and no write access, capped at 8 tool calls and 60 s per turn. **Privacy note:** your metric data leaves your infrastructure only to the Anthropic API, and only when this feature is enabled — without a key, the panel shows a setup card and nothing else degrades.

## API

Everything lives under `/v1` with `Authorization: Bearer hx_…` keys (scopes: `ingest`, `read`, `admin`). Interactive OpenAPI docs at [`http://localhost:8000/docs`](http://localhost:8000/docs).

| Method & path | Scope | Purpose |
|---|---|---|
| `POST /v1/runs` | ingest | Register a run; returns id + ingest hints |
| `POST /v1/ingest` | ingest | Batched metric points (≤500), idempotent by `client_batch_id` |
| `POST /v1/runs/{id}/heartbeat` | ingest | Liveness + progress; returns the kill directive |
| `POST /v1/runs/{id}/ack-kill` | ingest | Trainer confirms a graceful stop |
| `POST /v1/runs/{id}/complete` | ingest | Final status + metric value |
| `GET /v1/runs`, `GET /v1/runs/{id}` | read | List/detail with the latest forecast inline |
| `GET /v1/runs/{id}/metrics` | read | LTTB-downsampled series |
| `GET /v1/runs/{id}/forecasts` | read | Forecast history |
| `POST /v1/runs/{id}/kill` | admin | Manual kill, or `{"cancel": true}` to override |
| `GET/POST/PATCH /v1/policies` | read/admin | Policy CRUD (jsonschema-validated) |
| `POST /v1/policies/dry-run` | read | Replay a candidate rule against history |
| `GET /v1/events` | read | Policy event feed with snapshots |
| `GET /v1/calibration` | read | Reliability bins, Brier, calibrated flag |
| `GET /v1/ledger` | read | Recovered dollars, gross and expected |
| `GET /v1/stream` | read | SSE: `run.updated`, `forecast.updated`, `policy.fired`, `ledger.updated` |
| `GET /v1/copilot/status`, `POST /v1/copilot/chat` | read | The Analyst |
| `POST /v1/admin/keys` (+ list/revoke) | admin | Key management; plaintext shown once |
| `GET /healthz`, `GET /readyz` | none | Probes |

Rate limits per key: metric ingest 120 req/min (burst 240), copilot 10 req/min, everything else 300 req/min; 429s carry `Retry-After`.

## Configuration

All configuration is environment variables (pydantic-settings), documented in [`.env.example`](.env.example):

| Variable | Default | Purpose |
|---|---|---|
| `HARUSPEX_DATABASE_URL` | `postgresql+asyncpg://haruspex:haruspex@localhost:55432/haruspex` | Async SQLAlchemy URL for api + worker |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `haruspex` | Compose db credentials (change together) |
| `HARUSPEX_CORS_ORIGINS` | `http://localhost:5173,http://localhost:8080` | Browser-origin allowlist |
| `HARUSPEX_LOG_LEVEL` | `info` | structlog level |
| `HARUSPEX_WORKER_INTERVAL_S` | `15` | Seconds between forecast refits per run |
| `HARUSPEX_HEARTBEAT_STALE_S` | `120` | Heartbeats older than this mark a run LOST |
| `ANTHROPIC_API_KEY` | *(unset)* | Enables the Analyst; everything else works without it |
| `HARUSPEX_COPILOT_MODEL` | `claude-sonnet-4-6` | Analyst model |
| `HARUSPEX_API_URL` / `HARUSPEX_API_KEY` | — | SDK-side connection settings |

## Development

```
backend/   FastAPI app + worker (one package, two entrypoints)
sdk/       the `haruspex` Python package + simulator
frontend/  React 18 + TS strict + Tailwind v4 + d3 (see frontend/DESIGN.md)
deploy/    docker-compose, Dockerfiles, nginx
scripts/   smoke.sh, contract.sh, check_no_placeholders.sh, demo_seed.py
```

Setup: install [uv](https://docs.astral.sh/uv/), Node 22 + pnpm, Docker; then:

```bash
uv sync --all-packages          # one venv for backend + sdk
pnpm -C frontend install
make hooks                      # install the pre-commit commit gate (required)
make dev                        # db (compose) + api + worker hot-reload + vite
```

Make targets (`make help` prints this): `dev`, `demo`, `test`, `lint`, `typecheck`, `hooks`, `ci`, `smoke`, `contract`, `e2e`, `migrate`, `keys`, `clean`.

The test pyramid: pure unit tests (forecaster math at ≥95 % branch coverage, LTTB, policy evaluator, ledger, auth, rate limiter, SDK batching via `httpx.MockTransport`, framework callbacks on fake trainers, the Analyst loop with the Anthropic client mocked at the SDK boundary) → property tests (hypothesis: ingest idempotency, LTTB invariants, forecaster totality) → API integration tests against real Postgres → a schemathesis contract suite over the live OpenAPI schema → a compose smoke script → one Playwright spec against the full demo. Coverage gates: backend ≥85 %, sdk ≥90 %, frontend statements ≥70 %.

**Every CI job executes a Make target, so a green local `make ci` means green CI.** macOS note: if editable imports mysteriously vanish (`ModuleNotFoundError` though `uv pip list` shows the package), see the UF_HIDDEN entry in [DECISIONS.md](DECISIONS.md).

## Limitations & roadmap

Honest list, in rough priority order:

- **Single-tenant.** Auth is API keys with three scopes — no users, no orgs, no SSO. Put it behind your VPN.
- **In-process rate limiting and SSE fan-out.** Both are per-api-replica; running multiple api replicas multiplies limits and works, but limits aren't global, and there's no HA story for the worker (run exactly one).
- **The forecaster assumes loss-like curves.** Monotone-ish decay (or rise, for `direction: max`) toward an asymptote. Cyclic schedules with warm restarts, GAN losses, and RL returns will fit poorly — the martingale baseline keeps the forecasts sane, but the probabilities won't be sharp.
- **Calibration needs history.** Until 30 labeled runs, probabilities are raw and badged as such; small orgs live in that regime for a while.
- **Wall-clock ETA is linear extrapolation** from observed pace; it doesn't model multi-stage schedules.
- **No retention policy** — `metric_points` grows unboundedly; add partitioning or TTLs before very long deployments.
- Roadmap candidates: per-tag forecaster priors, warn-channel webhooks, multi-replica worker leases, W&B/MLflow importers, anomaly explanations on the trace itself.

## License

[MIT](LICENSE).
