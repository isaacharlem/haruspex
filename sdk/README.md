# haruspex

Python SDK for [Haruspex](../README.md): instrument ML training runs for live outcome
forecasting, budget kill policies, and recovered-GPU-spend accounting.

```python
import haruspex

run = haruspex.init(
    name="gpt2-small-bf16", tags=["pretrain"],
    target=("loss", 2.9, "min"),
    budget_steps=10_000, budget_wallclock_s=4 * 3600,
    gpu=("H100", 8),
)
for step in range(10_000):
    loss, grad_norm, lr = train_step()
    run.log(step=step, loss=loss, grad_norm=grad_norm, lr=lr)
    if run.should_stop():          # set by a Haruspex kill directive
        save_checkpoint()
        break
run.finish(status="completed", final={"loss": loss})
```

Also ships `haruspex-simulate`, a synthetic-run generator that exercises the same
public API — both the demo and a living integration test.
