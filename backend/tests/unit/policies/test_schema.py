import pytest

from haruspex_server.policies.schema import PolicyValidationError, validate_definition

BRIEF_EXAMPLE = {
    "name": "kill-doomed-after-warmup",
    "scope": {"tags": ["pretrain"]},
    "when": {
        "signal": "p_hit_target",
        "op": "<",
        "value": 0.05,
        "after_progress": 0.10,
        "sustained_evals": 3,
    },
    "action": {
        "type": "kill",
        "grace_seconds": 120,
        "min_checkpoint_age_seconds": 600,
        "notify": True,
    },
}


def test_brief_example_validates_unchanged() -> None:
    assert validate_definition(BRIEF_EXAMPLE) == BRIEF_EXAMPLE


def test_defaults_are_filled() -> None:
    minimal = {
        "name": "warn-slow",
        "when": {"signal": "progress", "op": ">=", "value": 0.5},
        "action": {"type": "warn"},
    }
    filled = validate_definition(minimal)
    assert filled["when"]["after_progress"] == 0.0
    assert filled["when"]["sustained_evals"] == 1
    assert filled["action"]["grace_seconds"] == 120
    assert filled["action"]["min_checkpoint_age_seconds"] == 0
    assert filled["action"]["notify"] is True
    assert filled["scope"] == {"tags": []}


def test_metric_signal_accepted() -> None:
    definition = {
        "name": "loss-ceiling",
        "when": {"signal": "metric:loss", "op": ">", "value": 10.0},
        "action": {"type": "warn"},
    }
    assert validate_definition(definition)["when"]["signal"] == "metric:loss"


@pytest.mark.parametrize(
    "mutation",
    [
        {"surprise": 1},
        {"when": {**BRIEF_EXAMPLE["when"], "unknown_field": True}},
        {"action": {**BRIEF_EXAMPLE["action"], "exec": "rm -rf"}},
        {"scope": {"tags": ["x"], "cluster": "a"}},
    ],
)
def test_unknown_fields_rejected(mutation: dict) -> None:
    definition = {**BRIEF_EXAMPLE, **mutation}
    with pytest.raises(PolicyValidationError):
        validate_definition(definition)


@pytest.mark.parametrize(
    "when_mutation",
    [
        {"signal": "p_doom"},
        {"signal": "metric:"},
        {"op": "=="},
        {"value": "high"},
        {"after_progress": 1.5},
        {"sustained_evals": 0},
    ],
)
def test_bad_when_values_rejected(when_mutation: dict) -> None:
    definition = {**BRIEF_EXAMPLE, "when": {**BRIEF_EXAMPLE["when"], **when_mutation}}
    with pytest.raises(PolicyValidationError):
        validate_definition(definition)


def test_bad_action_type_rejected() -> None:
    definition = {**BRIEF_EXAMPLE, "action": {**BRIEF_EXAMPLE["action"], "type": "page"}}
    with pytest.raises(PolicyValidationError):
        validate_definition(definition)


def test_missing_required_rejected() -> None:
    with pytest.raises(PolicyValidationError):
        validate_definition({"name": "x", "action": {"type": "warn"}})
