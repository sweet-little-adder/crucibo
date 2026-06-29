"""Train baseline MLP on Parquet ticks."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from morning_star.features.schema import FEATURE_DIM
from morning_star.io_parquet import filter_price_bars, parquet_to_ticks, sorted_ticks
from morning_star.models.baseline import BaselineMLP
from morning_star.train.dataset import build_supervised_rows, min_ticks_for_training


def _sigmoid(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, -60.0, 60.0)
    return 1.0 / (1.0 + np.exp(-x))


def train_baseline_mlp(
    ticks: list,
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
    rng = np.random.default_rng(seed)
    x, y = build_supervised_rows(
        ticks,
        lookback=lookback,
        forward_horizon=forward_horizon,
        initial_cash=initial_cash,
        max_position=target_shares,
    )

    w1 = rng.normal(0.0, 1.0 / math.sqrt(FEATURE_DIM), size=(FEATURE_DIM, hidden_dim))
    b1 = np.zeros((1, hidden_dim))
    w2 = rng.normal(0.0, 1.0 / math.sqrt(hidden_dim), size=(hidden_dim, 1))
    b2 = np.zeros((1, 1))

    for _ in range(epochs):
        h_pre = x @ w1 + b1
        h = np.tanh(h_pre)
        logit = h @ w2 + b2
        pred = _sigmoid(logit)
        error = pred - y

        grad_logit = error
        grad_w2 = h.T @ grad_logit
        grad_b2 = np.sum(grad_logit, axis=0, keepdims=True)
        grad_h = grad_logit @ w2.T
        grad_h_pre = grad_h * (1.0 - h**2)
        grad_w1 = x.T @ grad_h_pre
        grad_b1 = np.sum(grad_h_pre, axis=0, keepdims=True)

        w2 -= learning_rate * grad_w2
        b2 -= learning_rate * grad_b2
        w1 -= learning_rate * grad_w1
        b1 -= learning_rate * grad_b1

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


def train_from_parquet(
    *,
    ticks_path: Path,
    lookback: int = 20,
    forward_horizon: int = 5,
    hidden_dim: int = 8,
    epochs: int = 80,
    learning_rate: float = 0.05,
    seed: int = 42,
    threshold: float = 0.5,
    target_shares: int = 50,
    initial_cash: float = 1_000_000.0,
) -> tuple[BaselineMLP, list]:
    path = ticks_path.resolve()
    ticks = sorted_ticks(filter_price_bars(parquet_to_ticks(path)))
    need = min_ticks_for_training(lookback=lookback, forward_horizon=forward_horizon)
    if len(ticks) < need:
        raise ValueError(
            f"parquet has {len(ticks)} ticks; need at least {need} "
            f"(lookback={lookback}, forward_horizon={forward_horizon})"
        )
    model = train_baseline_mlp(
        ticks,
        lookback=lookback,
        forward_horizon=forward_horizon,
        hidden_dim=hidden_dim,
        epochs=epochs,
        learning_rate=learning_rate,
        seed=seed,
        threshold=threshold,
        target_shares=target_shares,
        initial_cash=initial_cash,
    )
    return model, ticks
