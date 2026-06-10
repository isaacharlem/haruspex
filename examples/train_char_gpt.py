"""A real training run instrumented with Haruspex.

Trains a small character-level GPT on Tiny Shakespeare with pure PyTorch
(MPS/CUDA/CPU) while streaming loss, grad-norm, and learning rate to a live
Haruspex server. Demonstrates the full SDK contract: non-blocking logging,
checkpoint reporting for the kill policy's checkpoint guard, the kill
directive (``should_stop``/``on_kill``), and completion accounting.

Usage:
    HARUSPEX_API_URL=http://localhost:8000 HARUSPEX_API_KEY=hx_... \
        python examples/train_char_gpt.py
"""

import math
import time
import urllib.request
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F

import haruspex

DATA_URL = (
    "https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt"
)
DATA_PATH = Path(__file__).parent / "data" / "tinyshakespeare.txt"
CKPT_PATH = Path(__file__).parent / "data" / "char_gpt.pt"

# Model / optimization
BLOCK_SIZE = 256
BATCH_SIZE = 64
N_LAYER = 6
N_HEAD = 8
D_MODEL = 256
DROPOUT = 0.1
MAX_STEPS = 6000
WARMUP_STEPS = 200
LR_MAX = 3e-4
LR_MIN = 1e-5
GRAD_CLIP = 1.0
EVAL_EVERY = 200
EVAL_BATCHES = 16
CKPT_EVERY = 500

TARGET_LOSS = 1.60


class Block(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.ln1 = nn.LayerNorm(D_MODEL)
        self.attn = nn.Linear(D_MODEL, 3 * D_MODEL)
        self.proj = nn.Linear(D_MODEL, D_MODEL)
        self.ln2 = nn.LayerNorm(D_MODEL)
        self.mlp = nn.Sequential(
            nn.Linear(D_MODEL, 4 * D_MODEL),
            nn.GELU(),
            nn.Linear(4 * D_MODEL, D_MODEL),
            nn.Dropout(DROPOUT),
        )
        self.drop = nn.Dropout(DROPOUT)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, t, _ = x.shape
        q, k, v = self.attn(self.ln1(x)).split(D_MODEL, dim=2)
        shape = (b, t, N_HEAD, D_MODEL // N_HEAD)
        q, k, v = (z.view(shape).transpose(1, 2) for z in (q, k, v))
        y = F.scaled_dot_product_attention(
            q, k, v, is_causal=True, dropout_p=DROPOUT if self.training else 0.0
        )
        y = y.transpose(1, 2).contiguous().view(b, t, D_MODEL)
        x = x + self.drop(self.proj(y))
        return x + self.mlp(self.ln2(x))


class CharGPT(nn.Module):
    def __init__(self, vocab_size: int) -> None:
        super().__init__()
        self.tok = nn.Embedding(vocab_size, D_MODEL)
        self.pos = nn.Embedding(BLOCK_SIZE, D_MODEL)
        self.drop = nn.Dropout(DROPOUT)
        self.blocks = nn.ModuleList(Block() for _ in range(N_LAYER))
        self.ln_f = nn.LayerNorm(D_MODEL)
        self.head = nn.Linear(D_MODEL, vocab_size, bias=False)
        self.head.weight = self.tok.weight  # weight tying

    def forward(self, idx: torch.Tensor) -> torch.Tensor:
        positions = torch.arange(idx.shape[1], device=idx.device)
        x = self.drop(self.tok(idx) + self.pos(positions))
        for block in self.blocks:
            x = block(x)
        return self.head(self.ln_f(x))


def load_corpus() -> str:
    if not DATA_PATH.exists():
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading tiny shakespeare to {DATA_PATH} ...")
        urllib.request.urlretrieve(DATA_URL, DATA_PATH)
    return DATA_PATH.read_text(encoding="utf-8")


def get_batch(data: torch.Tensor, device: torch.device) -> tuple[torch.Tensor, torch.Tensor]:
    starts = torch.randint(0, len(data) - BLOCK_SIZE - 1, (BATCH_SIZE,))
    x = torch.stack([data[s : s + BLOCK_SIZE] for s in starts])
    y = torch.stack([data[s + 1 : s + BLOCK_SIZE + 1] for s in starts])
    return x.to(device), y.to(device)


def lr_at(step: int) -> float:
    if step < WARMUP_STEPS:
        return LR_MAX * (step + 1) / WARMUP_STEPS
    progress = (step - WARMUP_STEPS) / max(1, MAX_STEPS - WARMUP_STEPS)
    return LR_MIN + 0.5 * (LR_MAX - LR_MIN) * (1 + math.cos(math.pi * progress))


@torch.no_grad()
def eval_loss(model: nn.Module, data: torch.Tensor, device: torch.device) -> float:
    model.eval()
    total = 0.0
    for _ in range(EVAL_BATCHES):
        x, y = get_batch(data, device)
        logits = model(x)
        total += F.cross_entropy(logits.view(-1, logits.shape[-1]), y.view(-1)).item()
    model.train()
    return total / EVAL_BATCHES


def main() -> None:
    torch.manual_seed(1337)
    device = torch.device(
        "mps"
        if torch.backends.mps.is_available()
        else "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    text = load_corpus()
    chars = sorted(set(text))
    stoi = {ch: i for i, ch in enumerate(chars)}
    encoded = torch.tensor([stoi[ch] for ch in text], dtype=torch.long)
    split = int(0.9 * len(encoded))
    train_data, val_data = encoded[:split], encoded[split:]

    model = CharGPT(len(chars)).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"device={device.type} vocab={len(chars)} params={n_params / 1e6:.2f}M")

    decay = [p for p in model.parameters() if p.dim() >= 2]
    no_decay = [p for p in model.parameters() if p.dim() < 2]
    optimizer = torch.optim.AdamW(
        [{"params": decay, "weight_decay": 0.1}, {"params": no_decay, "weight_decay": 0.0}],
        lr=LR_MAX,
        betas=(0.9, 0.95),
    )

    run = haruspex.init(
        "char-gpt-shakespeare",
        tags=["example", "local", "shakespeare"],
        target=("loss", TARGET_LOSS, "min"),
        budget_steps=MAX_STEPS,
        budget_wallclock_s=3600,
        gpu=("AppleSilicon", 1, 0.50),
        framework="pytorch",
        on_kill=lambda: print("haruspex directed a kill; checkpointing and stopping"),
    )

    def save_checkpoint(step: int) -> None:
        torch.save({"step": step, "model": model.state_dict(), "vocab": "".join(chars)}, CKPT_PATH)
        run.checkpoint_saved()

    model.train()
    started = time.time()
    loss_value = float("inf")
    for step in range(MAX_STEPS):
        lr = lr_at(step)
        for group in optimizer.param_groups:
            group["lr"] = lr

        x, y = get_batch(train_data, device)
        logits = model(x)
        loss = F.cross_entropy(logits.view(-1, logits.shape[-1]), y.view(-1))
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
        optimizer.step()

        loss_value = loss.item()
        run.log(step=step, loss=loss_value, grad_norm=grad_norm.item(), lr=lr)

        if step % EVAL_EVERY == 0 and step > 0:
            val = eval_loss(model, val_data, device)
            run.log(step=step, val_loss=val)
            pace = step / (time.time() - started)
            print(f"step {step:5d}  train {loss_value:.3f}  val {val:.3f}  {pace:.1f} it/s")

        if step % CKPT_EVERY == 0 and step > 0:
            save_checkpoint(step)

        if run.should_stop():
            save_checkpoint(step)
            break

    final_val = eval_loss(model, val_data, device)
    save_checkpoint(MAX_STEPS)
    run.finish(status="completed", final={"loss": final_val})
    print(f"finished: final val loss {final_val:.3f} (target {TARGET_LOSS}) run_id={run.run_id}")


if __name__ == "__main__":
    main()
