"""PyTorch MLP training — exports to numpy BaselineMLP for crucibo (no torch in crucibo)."""

from __future__ import annotations

from morning_star.features.schema import FEATURE_DIM
from morning_star.models.baseline import BaselineMLP
from morning_star.ticks import Tick
from morning_star.train.dataset import build_supervised_rows


def train_torch_mlp(
    ticks: list[Tick],
    *,
    lookback: int = 20,
    forward_horizon: int = 5,
    hidden_dim: int = 8,
    epochs: int = 80,
    learning_rate: float = 0.05,
    seed: int = 42,
    threshold: float = 0.5,
    target_shares: int = 50,
    initial_cash: float = 1_000_000.0,
) -> BaselineMLP:
    try:
        import torch
        import torch.nn as nn
    except ImportError as exc:
        raise ImportError(
            "PyTorch backend requires torch — pip install 'morning-star[torch]'"
        ) from exc

    torch.manual_seed(seed)
    x_np, y_np = build_supervised_rows(
        ticks,
        lookback=lookback,
        forward_horizon=forward_horizon,
        initial_cash=initial_cash,
        max_position=target_shares,
    )
    x = torch.from_numpy(x_np)
    y = torch.from_numpy(y_np)

    model = nn.Sequential(
        nn.Linear(FEATURE_DIM, hidden_dim),
        nn.Tanh(),
        nn.Linear(hidden_dim, 1),
    )
    loss_fn = nn.BCEWithLogitsLoss()
    optim = torch.optim.SGD(model.parameters(), lr=learning_rate)

    for _ in range(epochs):
        optim.zero_grad()
        logits = model(x)
        loss = loss_fn(logits, y)
        loss.backward()
        optim.step()

    linear1: nn.Linear = model[0]  # type: ignore[assignment]
    linear2: nn.Linear = model[2]  # type: ignore[assignment]
    w1 = linear1.weight.detach().numpy().T.copy()
    b1 = linear1.bias.detach().numpy().reshape(1, -1).copy()
    w2 = linear2.weight.detach().numpy().T.copy()
    b2 = linear2.bias.detach().numpy().reshape(1, -1).copy()

    return BaselineMLP(
        w1=w1,
        b1=b1,
        w2=w2,
        b2=b2,
        lookback=lookback,
        forward_horizon=forward_horizon,
        threshold=threshold,
        target_shares=target_shares,
        initial_cash=initial_cash,
    )
