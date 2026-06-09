"""Hugging Face Trainer integration.

``transformers`` is an optional dependency: when present, the callback
subclasses ``transformers.TrainerCallback``; otherwise it is a plain class
with the same hook methods, importable and testable against fakes.
"""

import logging
from typing import Any

from haruspex.run import Run

logger = logging.getLogger("haruspex")

try:
    from transformers import TrainerCallback as _TrainerCallback
except ImportError:
    _TrainerCallback = object

_METRIC_KEYS = {"loss", "grad_norm", "learning_rate", "eval_loss"}


class HaruspexCallback(_TrainerCallback):  # type: ignore[misc]
    """Logs Trainer metrics, honors kill directives by setting
    ``control.should_training_stop``, reports checkpoints, finalizes the run."""

    def __init__(self, run: Run):
        self.run = run

    def on_log(
        self,
        args: Any,
        state: Any,
        control: Any,
        logs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        if not logs:
            return
        step = int(getattr(state, "global_step", 0))
        metrics = {
            key: float(value)
            for key, value in logs.items()
            if key in _METRIC_KEYS and isinstance(value, int | float)
        }
        if metrics:
            self.run.log(step=step, **metrics)

    def on_step_end(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
        if self.run.should_stop():
            control.should_training_stop = True

    def on_save(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
        self.run.checkpoint_saved()

    def on_train_end(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
        self.run.finish(status="completed")
