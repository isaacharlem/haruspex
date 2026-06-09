"""Callback tests against minimal fake trainer objects (no frameworks installed)."""

from types import SimpleNamespace
from typing import Any

from haruspex.callbacks.lightning import HaruspexCallback as LightningCallback
from haruspex.callbacks.transformers import HaruspexCallback as TransformersCallback


class StubRun:
    def __init__(self, stop: bool = False) -> None:
        self.stop = stop
        self.logged: list[tuple[int, dict[str, float]]] = []
        self.checkpoints = 0
        self.finished: list[str] = []

    def log(self, *, step: int, **metrics: float) -> None:
        self.logged.append((step, metrics))

    def should_stop(self) -> bool:
        return self.stop

    def checkpoint_saved(self, ts: float | None = None) -> None:
        self.checkpoints += 1

    def finish(self, status: str = "completed", **kwargs: Any) -> None:
        self.finished.append(status)


class FakeTensor:
    def __init__(self, value: float) -> None:
        self.value = value

    def item(self) -> float:
        return self.value


def fake_lightning_trainer(step: int = 7, lr: float = 3e-4) -> SimpleNamespace:
    return SimpleNamespace(
        global_step=step,
        should_stop=False,
        optimizers=[SimpleNamespace(param_groups=[{"lr": lr}])],
    )


class TestLightningCallback:
    def test_logs_loss_and_lr(self) -> None:
        run = StubRun()
        callback = LightningCallback(run)  # type: ignore[arg-type]
        trainer = fake_lightning_trainer()
        callback.on_train_batch_end(trainer, None, {"loss": FakeTensor(3.2)}, None, 0)
        assert run.logged == [(7, {"loss": 3.2, "lr": 3e-4})]
        assert trainer.should_stop is False

    def test_tensor_outputs_without_mapping(self) -> None:
        run = StubRun()
        callback = LightningCallback(run)  # type: ignore[arg-type]
        callback.on_train_batch_end(fake_lightning_trainer(), None, FakeTensor(2.5), None, 0)
        assert run.logged[0][1]["loss"] == 2.5

    def test_kill_directive_sets_trainer_should_stop(self) -> None:
        run = StubRun(stop=True)
        callback = LightningCallback(run)  # type: ignore[arg-type]
        trainer = fake_lightning_trainer()
        callback.on_train_batch_end(trainer, None, {"loss": FakeTensor(1.0)}, None, 0)
        assert trainer.should_stop is True

    def test_checkpoint_and_fit_end(self) -> None:
        run = StubRun()
        callback = LightningCallback(run)  # type: ignore[arg-type]
        callback.on_save_checkpoint(None, None, {})
        callback.on_fit_end(None, None)
        assert run.checkpoints == 1
        assert run.finished == ["completed"]

    def test_exception_finishes_as_diverged(self) -> None:
        run = StubRun()
        callback = LightningCallback(run)  # type: ignore[arg-type]
        callback.on_exception(None, None, RuntimeError("nan loss"))
        assert run.finished == ["diverged"]

    def test_log_every_n_steps(self) -> None:
        run = StubRun()
        callback = LightningCallback(run, log_every_n_steps=2)  # type: ignore[arg-type]
        for step in range(4):
            trainer = fake_lightning_trainer(step=step)
            callback.on_train_batch_end(trainer, None, {"loss": FakeTensor(1.0)}, None, step)
        assert [step for step, _ in run.logged] == [0, 2]


def fake_hf_state(step: int = 11) -> SimpleNamespace:
    return SimpleNamespace(global_step=step)


class TestTransformersCallback:
    def test_logs_known_metrics_only(self) -> None:
        run = StubRun()
        callback = TransformersCallback(run)  # type: ignore[arg-type]
        callback.on_log(
            None,
            fake_hf_state(),
            SimpleNamespace(should_training_stop=False),
            logs={"loss": 2.1, "learning_rate": 1e-4, "epoch": 0.4, "note": "x"},
        )
        assert run.logged == [(11, {"loss": 2.1, "learning_rate": 1e-4})]

    def test_kill_directive_sets_control_flag(self) -> None:
        run = StubRun(stop=True)
        callback = TransformersCallback(run)  # type: ignore[arg-type]
        control = SimpleNamespace(should_training_stop=False)
        callback.on_step_end(None, fake_hf_state(), control)
        assert control.should_training_stop is True

    def test_save_and_train_end(self) -> None:
        run = StubRun()
        callback = TransformersCallback(run)  # type: ignore[arg-type]
        callback.on_save(None, fake_hf_state(), None)
        callback.on_train_end(None, fake_hf_state(), None)
        assert run.checkpoints == 1
        assert run.finished == ["completed"]

    def test_empty_logs_ignored(self) -> None:
        run = StubRun()
        callback = TransformersCallback(run)  # type: ignore[arg-type]
        callback.on_log(None, fake_hf_state(), None, logs=None)
        assert run.logged == []
