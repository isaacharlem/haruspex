"""Policy definition schema (§8 of the build brief).

Validated with jsonschema on every write; unknown fields are rejected at
every level (``additionalProperties: false``).
"""

from typing import Any

import jsonschema

SIGNALS = ("p_hit_target", "p_diverge", "p_plateau", "progress")
METRIC_SIGNAL_PATTERN = r"^metric:[A-Za-z0-9_.\-/]{1,100}$"
OPS = ("<", "<=", ">", ">=")
ACTION_TYPES = ("warn", "kill")

POLICY_DEFINITION_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "when", "action"],
    "properties": {
        "name": {"type": "string", "minLength": 1, "maxLength": 200},
        "scope": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1, "maxLength": 100},
                    "maxItems": 20,
                }
            },
        },
        "when": {
            "type": "object",
            "additionalProperties": False,
            "required": ["signal", "op", "value"],
            "properties": {
                "signal": {
                    "anyOf": [
                        {"enum": list(SIGNALS)},
                        {"type": "string", "pattern": METRIC_SIGNAL_PATTERN},
                    ]
                },
                "op": {"enum": list(OPS)},
                "value": {"type": "number"},
                "after_progress": {"type": "number", "minimum": 0, "maximum": 1},
                "sustained_evals": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        },
        "action": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type"],
            "properties": {
                "type": {"enum": list(ACTION_TYPES)},
                "grace_seconds": {"type": "integer", "minimum": 0, "maximum": 3600},
                "min_checkpoint_age_seconds": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 86_400,
                },
                "notify": {"type": "boolean"},
            },
        },
    },
}

DEFAULTS = {
    "after_progress": 0.0,
    "sustained_evals": 1,
    "grace_seconds": 120,
    "min_checkpoint_age_seconds": 0,
    "notify": True,
}


class PolicyValidationError(ValueError):
    pass


def validate_definition(definition: dict[str, Any]) -> dict[str, Any]:
    """Validate and return the definition with defaults filled in."""
    try:
        jsonschema.validate(definition, POLICY_DEFINITION_SCHEMA)
    except jsonschema.ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path) or "definition"
        raise PolicyValidationError(f"{path}: {exc.message}") from exc

    filled = {
        "name": definition["name"],
        "scope": {"tags": list(definition.get("scope", {}).get("tags", []))},
        "when": {
            "signal": definition["when"]["signal"],
            "op": definition["when"]["op"],
            "value": definition["when"]["value"],
            "after_progress": definition["when"].get("after_progress", DEFAULTS["after_progress"]),
            "sustained_evals": definition["when"].get(
                "sustained_evals", DEFAULTS["sustained_evals"]
            ),
        },
        "action": {
            "type": definition["action"]["type"],
            "grace_seconds": definition["action"].get("grace_seconds", DEFAULTS["grace_seconds"]),
            "min_checkpoint_age_seconds": definition["action"].get(
                "min_checkpoint_age_seconds", DEFAULTS["min_checkpoint_age_seconds"]
            ),
            "notify": definition["action"].get("notify", DEFAULTS["notify"]),
        },
    }
    return filled
