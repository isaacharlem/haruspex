# Decisions

One line per decision the build brief left open. Newest at the bottom.

- Repo lives at the workspace root (no extra `haruspex/` nesting) since the directory is the repo.
- uv workspace uses a virtual root `pyproject.toml` (workspace + shared tool config only); members are `backend` and `sdk`, synced into one root `.venv`.
- Package build backend is `hatchling` for both Python packages (uv default, boring, supports src layout).
- Shared ruff config lives in the root `pyproject.toml`; line length 100, py312 target.
- mypy: sdk runs `--strict`; backend config sets `disallow_untyped_defs` globally and enables the full strict flag set per-module for `forecaster.*` and `policies.*` (equivalent to `--strict` for those packages, avoids import-root issues of running mypy on subpackage paths).
- SDK runtime deps are only `httpx` + `numpy`; SDK uses stdlib `logging` (structlog is a backend-only dependency).
- `haruspex-simulate` CLI writes user-facing output via a `sys.stdout.write` helper so the mechanical `print(` audit stays simple and exception-free.
- Frontend package manager is pnpm (lockfile committed); React pinned to 18.x per brief even though 19 is current.
- Frontend never uses the HTML `placeholder` attribute (the placeholder audit greps for the word); inputs get visible labels or hints instead.
- Single dark theme only; it is an instrument (per §13.2).
- Forecaster deviation (measured, not stylistic): the curve head fits the raw target-metric series — `least_squares(loss="soft_l1")` provides the robustness, while fitting the EWMA(0.1)-smoothed series biases extrapolated finals upward by its group delay (~9 steps), failing the brief's own healthy-profile behavioral criterion (8/50 vs 50/50). EWMA(0.1) remains the smoothing for the divergence head and display series.
- Compose publishes Postgres on host port 55432 (not 5432) so `make demo` never collides with a host-local Postgres; in-network services still use `db:5432`.
- macOS note: uv re-marks `.venv` UF_HIDDEN on every install and CPython >= 3.12.13 skips hidden `.pth` files, breaking editable imports; tests sidestep it via pytest `pythonpath = ["src"]`, runtime make targets depend on `fix-venv` (`chflags -R nohidden .venv`, no-op elsewhere). Linux/CI/Docker unaffected.
