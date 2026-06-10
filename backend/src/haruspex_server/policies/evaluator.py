"""Pure policy evaluation with hysteresis and the checkpoint guard.

The engine is deliberately DB-free: the worker feeds it
:class:`EvaluationContext` values and acts on the returned decisions. Trip
counts live in engine memory — a worker restart resets hysteresis, which only
delays a fire by ``sustained_evals`` cycles (documented in DECISIONS.md).
"""

from dataclasses import dataclass, field
from typing import Any, Literal

Verdict = Literal["none", "warn", "kill", "deferred"]


@dataclass(frozen=True)
class EvaluationContext:
    """Everything one policy evaluation needs about one run, at one refit."""

    run_id: int
    tags: tuple[str, ...]
    progress: float
    p_hit_target: float
    p_diverge: float
    p_plateau: float
    metrics: dict[str, float] = field(default_factory=dict)
    checkpoint_age_s: float | None = None


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    sustained_count: int = 0
    signal_value: float | None = None
    deferred_for_s: float | None = None

    @property
    def fired(self) -> bool:
        return self.verdict in ("warn", "kill")


def matches_scope(definition: dict[str, Any], tags: tuple[str, ...]) -> bool:
    """A run is in scope when it carries at least one of the scope tags
    (an empty scope matches every run)."""
    scope_tags = definition.get("scope", {}).get("tags", [])
    if not scope_tags:
        return True
    return bool(set(scope_tags) & set(tags))


def signal_value(definition: dict[str, Any], ctx: EvaluationContext) -> float | None:
    signal = definition["when"]["signal"]
    if signal == "p_hit_target":
        return ctx.p_hit_target
    if signal == "p_diverge":
        return ctx.p_diverge
    if signal == "p_plateau":
        return ctx.p_plateau
    if signal == "progress":
        return ctx.progress
    if signal.startswith("metric:"):
        return ctx.metrics.get(signal.removeprefix("metric:"))
    return None


def condition_tripped(definition: dict[str, Any], ctx: EvaluationContext) -> bool:
    when = definition["when"]
    if ctx.progress < when["after_progress"]:
        return False
    value = signal_value(definition, ctx)
    if value is None:
        return False
    threshold = float(when["value"])
    op = when["op"]
    if op == "<":
        return value < threshold
    if op == "<=":
        return value <= threshold
    if op == ">":
        return value > threshold
    return value >= threshold


class PolicyEngine:
    """Stateful hysteresis + checkpoint-guard tracking across refits."""

    def __init__(self) -> None:
        self._trips: dict[tuple[int, int], int] = {}
        self._deferred_since: dict[tuple[int, int], float] = {}
        self._already_fired: set[tuple[int, int]] = set()

    def evaluate(
        self,
        policy_id: int,
        definition: dict[str, Any],
        ctx: EvaluationContext,
        *,
        now_s: float,
    ) -> Decision:
        """One evaluation of one policy against one run's fresh forecast.

        ``now_s`` is a monotonic-ish clock (seconds) used only to measure how
        long a kill has been deferred by the checkpoint guard.
        """
        key = (policy_id, ctx.run_id)
        if key in self._already_fired or not matches_scope(definition, ctx.tags):
            return Decision(verdict="none")

        if not condition_tripped(definition, ctx):
            self._trips[key] = 0
            self._deferred_since.pop(key, None)
            return Decision(verdict="none")

        count = self._trips.get(key, 0) + 1
        self._trips[key] = count
        value = signal_value(definition, ctx)
        when = definition["when"]
        if count < int(when["sustained_evals"]):
            return Decision(verdict="none", sustained_count=count, signal_value=value)

        action = definition["action"]
        if action["type"] == "warn":
            self._already_fired.add(key)
            return Decision(verdict="warn", sustained_count=count, signal_value=value)

        min_age = float(action["min_checkpoint_age_seconds"])
        if min_age > 0 and (ctx.checkpoint_age_s is None or ctx.checkpoint_age_s > min_age):
            # No fresh-enough checkpoint: defer the kill until one lands.
            self._deferred_since.setdefault(key, now_s)
            return Decision(
                verdict="deferred",
                sustained_count=count,
                signal_value=value,
                deferred_for_s=now_s - self._deferred_since[key],
            )

        deferred_for = now_s - self._deferred_since.pop(key, now_s)
        self._already_fired.add(key)
        return Decision(
            verdict="kill",
            sustained_count=count,
            signal_value=value,
            deferred_for_s=deferred_for if deferred_for > 0 else None,
        )

    def forget_run(self, run_id: int) -> None:
        """Drop state for a run that reached a terminal status."""
        for store in (self._trips, self._deferred_since):
            for key in [k for k in store if k[1] == run_id]:
                store.pop(key, None)
        self._already_fired -= {k for k in self._already_fired if k[1] == run_id}
