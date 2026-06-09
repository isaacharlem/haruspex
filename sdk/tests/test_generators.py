import numpy as np
import pytest

from haruspex.simulate.generators import PROFILES, generate

N = 600
TARGET = 2.9


def test_same_seed_is_deterministic() -> None:
    for profile in PROFILES:
        a = generate(profile, n_steps=N, target=TARGET, seed=7)
        b = generate(profile, n_steps=N, target=TARGET, seed=7)
        np.testing.assert_array_equal(a.loss, b.loss)
        np.testing.assert_array_equal(a.grad_norm, b.grad_norm)
        np.testing.assert_array_equal(a.lr, b.lr)


def test_unknown_profile_rejected() -> None:
    with pytest.raises(ValueError, match="unknown profile"):
        generate("catastrophic", n_steps=N, target=TARGET, seed=1)


@pytest.mark.parametrize("seed", range(20))
def test_healthy_reaches_target(seed: int) -> None:
    run = generate("healthy", n_steps=N, target=TARGET, seed=seed)
    assert run.final_status == "completed"
    assert run.hits_target
    assert np.isfinite(run.loss).all()


@pytest.mark.parametrize("seed", range(20))
def test_divergent_blows_up_with_grad_precursor(seed: int) -> None:
    run = generate("divergent", n_steps=N, target=TARGET, seed=seed)
    assert run.final_status == "diverged"
    assert not run.hits_target
    assert np.isnan(run.loss).any(), "divergence must end in NaN"

    break_at = int(run.params["break_at"])
    precursor = int(run.params["precursor"])
    start = max(0, break_at - precursor)
    # Grad norm rises through the precursor window...
    grad_window = run.grad_norm[start : break_at + 1]
    assert grad_window[-1] > grad_window[0] * 1.5
    # ...while the loss has not yet jumped at the breakpoint itself.
    healthy_ref = generate("healthy", n_steps=N, target=TARGET, seed=seed)
    assert run.loss[start] == pytest.approx(run.loss[start])
    assert abs(run.loss[break_at] - healthy_ref.loss[break_at]) < TARGET


@pytest.mark.parametrize("seed", range(20))
def test_plateau_stays_above_target(seed: int) -> None:
    run = generate("plateau", n_steps=N, target=TARGET, seed=seed)
    assert run.final_status == "completed"
    assert not run.hits_target
    # The asymptote keeps even the noisy tail clearly above target.
    tail = run.loss[-50:]
    assert float(np.median(tail)) > TARGET * 1.05


@pytest.mark.parametrize("seed", range(10))
def test_straggler_is_slow_but_healthy(seed: int) -> None:
    run = generate("straggler", n_steps=N, target=TARGET, seed=seed)
    assert 2.0 <= run.pace_factor <= 3.0
    assert run.hits_target


@pytest.mark.parametrize("seed", range(20))
def test_spiky_recoverer_spikes_then_recovers(seed: int) -> None:
    run = generate("spiky_recoverer", n_steps=N, target=TARGET, seed=seed)
    healthy_ref = generate("healthy", n_steps=N, target=TARGET, seed=seed)
    # There is at least one visible spike above the underlying trend...
    assert float(np.max(run.loss - healthy_ref.loss)) > TARGET * 0.3
    # ...but the run recovers and still reaches its target.
    assert run.hits_target
    assert np.isfinite(run.loss).all()


def test_lr_schedule_warms_up_then_decays() -> None:
    run = generate("healthy", n_steps=N, target=TARGET, seed=3)
    warmup = int(0.05 * N)
    assert run.lr[0] < run.lr[warmup]
    assert run.lr[-1] < run.lr[warmup]
