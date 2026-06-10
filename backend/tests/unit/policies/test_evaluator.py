from haruspex_server.policies.evaluator import (
    EvaluationContext,
    PolicyEngine,
    condition_tripped,
    matches_scope,
    signal_value,
)
from haruspex_server.policies.schema import validate_definition


def make_definition(**overrides: object) -> dict:
    base = {
        "name": "kill-diverging",
        "scope": {"tags": []},
        "when": {
            "signal": "p_diverge",
            "op": ">=",
            "value": 0.85,
            "after_progress": 0.1,
            "sustained_evals": 3,
        },
        "action": {"type": "kill", "grace_seconds": 60, "min_checkpoint_age_seconds": 0},
    }
    when = {**base["when"], **overrides.pop("when", {})}  # type: ignore[arg-type]
    action = {**base["action"], **overrides.pop("action", {})}  # type: ignore[arg-type]
    return validate_definition({**base, **overrides, "when": when, "action": action})


def make_ctx(**overrides: object) -> EvaluationContext:
    defaults: dict = {
        "run_id": 1,
        "tags": ("pretrain",),
        "progress": 0.5,
        "p_hit_target": 0.5,
        "p_diverge": 0.9,
        "p_plateau": 0.1,
        "metrics": {"loss": 3.2},
        "checkpoint_age_s": 30.0,
    }
    defaults.update(overrides)
    return EvaluationContext(**defaults)


class TestScopeAndSignals:
    def test_empty_scope_matches_everything(self) -> None:
        assert matches_scope(make_definition(), ("anything",))

    def test_tag_scope_requires_overlap(self) -> None:
        definition = make_definition(scope={"tags": ["pretrain"]})
        assert matches_scope(definition, ("pretrain", "big"))
        assert not matches_scope(definition, ("finetune",))

    def test_signal_extraction(self) -> None:
        ctx = make_ctx()
        assert signal_value(make_definition(), ctx) == 0.9
        assert signal_value(make_definition(when={"signal": "p_hit_target"}), ctx) == 0.5
        assert signal_value(make_definition(when={"signal": "p_plateau"}), ctx) == 0.1
        assert signal_value(make_definition(when={"signal": "progress"}), ctx) == 0.5
        assert signal_value(make_definition(when={"signal": "metric:loss"}), ctx) == 3.2
        assert signal_value(make_definition(when={"signal": "metric:acc"}), ctx) is None

    def test_ops(self) -> None:
        ctx = make_ctx(p_diverge=0.5)
        assert condition_tripped(make_definition(when={"op": ">=", "value": 0.5}), ctx)
        assert not condition_tripped(make_definition(when={"op": ">", "value": 0.5}), ctx)
        assert condition_tripped(make_definition(when={"op": "<=", "value": 0.5}), ctx)
        assert not condition_tripped(make_definition(when={"op": "<", "value": 0.5}), ctx)

    def test_after_progress_gates(self) -> None:
        definition = make_definition(when={"after_progress": 0.3})
        assert not condition_tripped(definition, make_ctx(progress=0.2))
        assert condition_tripped(definition, make_ctx(progress=0.4))


class TestHysteresis:
    def test_fires_only_after_sustained_evals(self) -> None:
        engine = PolicyEngine()
        definition = make_definition()
        ctx = make_ctx()
        assert engine.evaluate(1, definition, ctx, now_s=0).verdict == "none"
        assert engine.evaluate(1, definition, ctx, now_s=1).verdict == "none"
        decision = engine.evaluate(1, definition, ctx, now_s=2)
        assert decision.verdict == "kill"
        assert decision.sustained_count == 3
        assert decision.signal_value == 0.9

    def test_non_trip_resets_the_count(self) -> None:
        engine = PolicyEngine()
        definition = make_definition()
        engine.evaluate(1, definition, make_ctx(), now_s=0)
        engine.evaluate(1, definition, make_ctx(), now_s=1)
        engine.evaluate(1, definition, make_ctx(p_diverge=0.1), now_s=2)  # recovers
        assert engine.evaluate(1, definition, make_ctx(), now_s=3).verdict == "none"
        assert engine.evaluate(1, definition, make_ctx(), now_s=4).verdict == "none"
        assert engine.evaluate(1, definition, make_ctx(), now_s=5).verdict == "kill"

    def test_runs_and_policies_tracked_independently(self) -> None:
        engine = PolicyEngine()
        definition = make_definition(when={"sustained_evals": 2})
        engine.evaluate(1, definition, make_ctx(run_id=1), now_s=0)
        engine.evaluate(1, definition, make_ctx(run_id=2), now_s=0)
        assert engine.evaluate(1, definition, make_ctx(run_id=1), now_s=1).verdict == "kill"

    def test_fires_once_per_policy_run(self) -> None:
        engine = PolicyEngine()
        definition = make_definition(when={"sustained_evals": 1})
        assert engine.evaluate(1, definition, make_ctx(), now_s=0).verdict == "kill"
        assert engine.evaluate(1, definition, make_ctx(), now_s=1).verdict == "none"

    def test_forget_run_clears_state(self) -> None:
        engine = PolicyEngine()
        definition = make_definition(when={"sustained_evals": 1})
        engine.evaluate(1, definition, make_ctx(), now_s=0)
        engine.forget_run(1)
        assert engine.evaluate(1, definition, make_ctx(), now_s=1).verdict == "kill"


class TestWarn:
    def test_warn_fires_and_does_not_repeat(self) -> None:
        engine = PolicyEngine()
        definition = make_definition(when={"sustained_evals": 1}, action={"type": "warn"})
        assert engine.evaluate(1, definition, make_ctx(), now_s=0).verdict == "warn"
        assert engine.evaluate(1, definition, make_ctx(), now_s=1).verdict == "none"


class TestCheckpointGuard:
    def test_kill_deferred_until_fresh_checkpoint(self) -> None:
        engine = PolicyEngine()
        definition = make_definition(
            when={"sustained_evals": 1},
            action={"min_checkpoint_age_seconds": 600},
        )
        stale = make_ctx(checkpoint_age_s=4000.0)
        first = engine.evaluate(1, definition, stale, now_s=0)
        assert first.verdict == "deferred"
        second = engine.evaluate(1, definition, stale, now_s=30)
        assert second.verdict == "deferred"
        assert second.deferred_for_s == 30

        fresh = make_ctx(checkpoint_age_s=120.0)
        fired = engine.evaluate(1, definition, fresh, now_s=60)
        assert fired.verdict == "kill"
        assert fired.deferred_for_s == 60

    def test_missing_checkpoint_defers(self) -> None:
        engine = PolicyEngine()
        definition = make_definition(
            when={"sustained_evals": 1},
            action={"min_checkpoint_age_seconds": 600},
        )
        decision = engine.evaluate(1, definition, make_ctx(checkpoint_age_s=None), now_s=0)
        assert decision.verdict == "deferred"

    def test_zero_min_age_skips_guard(self) -> None:
        engine = PolicyEngine()
        definition = make_definition(when={"sustained_evals": 1})
        decision = engine.evaluate(1, definition, make_ctx(checkpoint_age_s=None), now_s=0)
        assert decision.verdict == "kill"
