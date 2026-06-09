"""Seeded synthetic loss/grad-norm/lr curve generators, one per failure mode.

Profiles:

- ``healthy``: pow3 decay ``c + a*t^(-b)`` + AR(1) noise; reaches its target.
- ``divergent``: healthy until a breakpoint, then a grad-norm precursor (3-8
  steps of rising deltas *before* the loss moves) followed by exponential
  blow-up into NaN.
- ``plateau``: exp3 decay with an asymptote 10-30 % above target.
- ``straggler``: a healthy curve that takes 2-3x the budgeted wall-clock per
  step (exercises ETA math).
- ``spiky_recoverer``: 1-2 loss spikes that fully recover; forecasters must
  not doom it (anti-trigger-happiness regression profile).
"""

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]

PROFILES = ("healthy", "divergent", "plateau", "straggler", "spiky_recoverer")


@dataclass(frozen=True)
class GeneratedRun:
    profile: str
    n_steps: int
    target: float
    loss: FloatArray
    grad_norm: FloatArray
    lr: FloatArray
    pace_factor: float
    """Wall-clock seconds per step relative to the budget assumption."""
    final_status: str
    """'completed' or 'diverged' — what an honest trainer would report."""
    params: dict[str, float] = field(default_factory=dict)

    @property
    def final_loss(self) -> float:
        finite = self.loss[np.isfinite(self.loss)]
        return float(finite[-1]) if len(finite) else float("nan")

    @property
    def hits_target(self) -> bool:
        return bool(np.isfinite(self.final_loss) and self.final_loss <= self.target)


def _lr_schedule(n: int, rng: np.random.Generator) -> FloatArray:
    """Cosine decay with 5% linear warmup."""
    peak = float(rng.uniform(1e-4, 6e-4))
    floor = peak * 0.1
    steps = np.arange(n, dtype=np.float64)
    warmup = max(1, int(0.05 * n))
    lr = np.where(
        steps < warmup,
        peak * (steps + 1) / warmup,
        floor + 0.5 * (peak - floor) * (1 + np.cos(np.pi * (steps - warmup) / max(1, n - warmup))),
    )
    return np.asarray(lr, dtype=np.float64)


def _ar1_noise(n: int, sigma: float, rng: np.random.Generator, rho: float = 0.9) -> FloatArray:
    shocks = rng.normal(0.0, sigma, size=n)
    noise = np.empty(n, dtype=np.float64)
    acc = 0.0
    for i in range(n):
        acc = rho * acc + shocks[i]
        noise[i] = acc
    return noise


def _grad_norm_base(n: int, rng: np.random.Generator) -> FloatArray:
    t = (np.arange(n, dtype=np.float64) + 1) / n
    base = rng.uniform(0.8, 2.0)
    decay = rng.uniform(0.2, 0.5)
    return np.asarray(base * t**-decay * 0.5 + base * 0.5, dtype=np.float64) * np.exp(
        rng.normal(0.0, 0.08, size=n)
    )


def _pow3_curve(
    n: int, target: float, rng: np.random.Generator, *, final_margin: tuple[float, float]
) -> tuple[FloatArray, dict[str, float]]:
    t = (np.arange(n, dtype=np.float64) + 1) / n
    b = float(rng.uniform(0.3, 0.7))
    final = target * float(rng.uniform(*final_margin))
    initial = target * float(rng.uniform(1.8, 3.0))
    a = (initial - final) / (float(n) ** b - 1.0)
    c = final - a
    curve = c + a * t**-b
    return np.asarray(curve, dtype=np.float64), {"a": a, "b": b, "c": c, "final": final}


def _healthy(n: int, target: float, rng: np.random.Generator) -> GeneratedRun:
    curve, params = _pow3_curve(n, target, rng, final_margin=(0.93, 0.985))
    noise = _ar1_noise(n, sigma=target * float(rng.uniform(0.004, 0.012)), rng=rng)
    return GeneratedRun(
        profile="healthy",
        n_steps=n,
        target=target,
        loss=curve + noise,
        grad_norm=_grad_norm_base(n, rng),
        lr=_lr_schedule(n, rng),
        pace_factor=float(rng.uniform(0.85, 1.1)),
        final_status="completed",
        params=params,
    )


def _divergent(n: int, target: float, rng: np.random.Generator) -> GeneratedRun:
    healthy = _healthy(n, target, rng)
    loss = healthy.loss.copy()
    grad = healthy.grad_norm.copy()
    break_at = int(n * float(rng.uniform(0.15, 0.5)))
    precursor = int(rng.integers(3, 9))
    precursor_start = max(0, break_at - precursor)

    # Grad-norm rises for `precursor` steps BEFORE the loss moves at all.
    grad[precursor_start:break_at] *= np.cumprod(
        np.full(break_at - precursor_start, float(rng.uniform(1.25, 1.6)))
    )
    growth = float(rng.uniform(0.08, 0.2))
    after = np.arange(n - break_at, dtype=np.float64)
    loss[break_at:] = loss[break_at] * np.exp(growth * after)
    grad[break_at:] = grad[max(0, break_at - 1)] * np.exp(growth * 1.5 * after)
    blown = loss > 1e8
    loss[blown] = np.nan
    grad[loss != loss] = np.nan
    return GeneratedRun(
        profile="divergent",
        n_steps=n,
        target=target,
        loss=loss,
        grad_norm=grad,
        lr=healthy.lr,
        pace_factor=healthy.pace_factor,
        final_status="diverged",
        params={**healthy.params, "break_at": float(break_at), "precursor": float(precursor)},
    )


def _plateau(n: int, target: float, rng: np.random.Generator) -> GeneratedRun:
    t = (np.arange(n, dtype=np.float64) + 1) / n
    c = target * float(rng.uniform(1.10, 1.30))
    initial = target * float(rng.uniform(1.8, 3.0))
    b = float(rng.uniform(3.0, 6.0))
    a = (initial - c) / float(np.exp(-b / n))
    curve = c + a * np.exp(-b * t)
    noise = _ar1_noise(n, sigma=target * float(rng.uniform(0.004, 0.012)), rng=rng)
    return GeneratedRun(
        profile="plateau",
        n_steps=n,
        target=target,
        loss=np.asarray(curve, dtype=np.float64) + noise,
        grad_norm=_grad_norm_base(n, rng) * 0.6,
        lr=_lr_schedule(n, rng),
        pace_factor=float(rng.uniform(0.85, 1.1)),
        final_status="completed",
        params={"a": a, "b": b, "c": c},
    )


def _straggler(n: int, target: float, rng: np.random.Generator) -> GeneratedRun:
    healthy = _healthy(n, target, rng)
    return GeneratedRun(
        profile="straggler",
        n_steps=n,
        target=target,
        loss=healthy.loss,
        grad_norm=healthy.grad_norm,
        lr=healthy.lr,
        pace_factor=float(rng.uniform(2.0, 3.0)),
        final_status="completed",
        params=healthy.params,
    )


def _spiky_recoverer(n: int, target: float, rng: np.random.Generator) -> GeneratedRun:
    healthy = _healthy(n, target, rng)
    loss = healthy.loss.copy()
    grad = healthy.grad_norm.copy()
    for _ in range(int(rng.integers(1, 3))):
        at = int(n * float(rng.uniform(0.2, 0.8)))
        width = int(rng.integers(5, 16))
        height = float(rng.uniform(1.5, 3.0))
        end = min(n, at + width)
        ramp = np.exp(-np.arange(end - at, dtype=np.float64) / max(2.0, width / 3.0))
        loss[at:end] += loss[at] * (height - 1.0) * ramp
        grad[at:end] *= 1.0 + float(rng.uniform(2.0, 7.0)) * ramp
    return GeneratedRun(
        profile="spiky_recoverer",
        n_steps=n,
        target=target,
        loss=loss,
        grad_norm=grad,
        lr=healthy.lr,
        pace_factor=healthy.pace_factor,
        final_status="completed",
        params=healthy.params,
    )


def generate(profile: str, *, n_steps: int, target: float, seed: int) -> GeneratedRun:
    """Generate one deterministic synthetic run."""
    rng = np.random.default_rng(seed)
    generators = {
        "healthy": _healthy,
        "divergent": _divergent,
        "plateau": _plateau,
        "straggler": _straggler,
        "spiky_recoverer": _spiky_recoverer,
    }
    if profile not in generators:
        raise ValueError(f"unknown profile {profile!r}; expected one of {PROFILES}")
    return generators[profile](n_steps, target, rng)
