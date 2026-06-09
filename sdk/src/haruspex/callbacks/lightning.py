"""PyTorch Lightning integration.

``lightning`` is an optional dependency: when present, the callback subclasses
``lightning.pytorch.Callback``; otherwise it is a plain class with the same
hook methods, so it stays importable and unit-testable against fake trainers.
"""

import logging
from collections.abc import Mapping
from typing import Any

from haruspex.run import Run

logger = logging.getLogger("haruspex")

try:
    from lightning.pytorch import Callback as _LightningCallback
except ImportError:
    _LightningCallback = object


def _to_float(value: Any) -> float | None:
    """Best-effort scalar extraction from floats and 0-dim tensors."""
    if isinstance(value, int | float):
        return float(value)
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return float(item())
        except (TypeError, ValueError):
            return None
    return None


class HaruspexCallback(_LightningCallback):  # type: ignore[misc]
    """Logs the loss/lr each batch, honors kill directives by setting
    ``trainer.should_stop``, reports checkpoints, and finalizes the run."""

    def __init__(self, run: Run, *, log_every_n_steps: int = 1):
        self.run = run
        self.log_every_n_steps = max(1, log_every_n_steps)

    def on_train_batch_end(
        self,
        trainer: Any,
        pl_module: Any,
        outputs: Any,
        batch: Any,
        batch_idx: int,
    ) -> None:
        step = int(getattr(trainer, "global_step", batch_idx))
        if step % self.log_every_n_steps == 0:
            metrics: dict[str, float] = {}
            loss = (
                _to_float(outputs.get("loss"))
                if isinstance(outputs, Mapping)
                else _to_float(outputs)
            )
            if loss is not None:
                metrics["loss"] = loss
            lr = self._current_lr(trainer)
            if lr is not None:
                metrics["lr"] = lr
            if metrics:
                self.run.log(step=step, **metrics)
        if self.run.should_stop():
            trainer.should_stop = True

    def on_save_checkpoint(self, trainer: Any, pl_module: Any, checkpoint: Any) -> None:
        self.run.checkpoint_saved()

    def on_fit_end(self, trainer: Any, pl_module: Any) -> None:
        self.run.finish(status="completed")

    def on_exception(self, trainer: Any, pl_module: Any, exception: BaseException) -> None:
        logger.warning("haruspex: training raised %r; finishing run as diverged", exception)
        self.run.finish(status="diverged")

    @staticmethod
    def _current_lr(trainer: Any) -> float | None:
        optimizers = getattr(trainer, "optimizers", None) or []
        for optimizer in optimizers:
            for group in getattr(optimizer, "param_groups", []):
                lr = _to_float(group.get("lr"))
                if lr is not None:
                    return lr
        return None
