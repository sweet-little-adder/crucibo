"""Small numpy MLP — train offline, load into ``NeuralStrategy`` at replay time."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from crucibo.features import FEATURE_DIM, FeatureState
from crucibo.io_parquet import parquet_to_ticks
from crucibo.models import TradeTick


@dataclass(frozen=True)
class MLPModel:
    w1: np.ndarray
    b1: np.ndarray
    w2: np.ndarray
    b2: np.ndarray
    lookback: int
    forward_horizon: int
    threshold: float
    target_shares: int
    initial_cash: float

    @property
    def hidden_dim(self) -> int:
        return int(self.w1.shape[1])

    def predict_proba(self, features: np.ndarray) -> float:
        x = np.asarray(features, dtype=np.float64).reshape(1, -1)
        h = np.tanh(x @ self.w1 + self.b1)
        logit = float(np.clip((h @ self.w2 + self.b2).item(), -60.0, 60.0))
        return 1.0 / (1.0 + math.exp(-logit))

    def decide_shares(self, features: np.ndarray) -> int:
        prob = self.predict_proba(features)
        return self.target_shares if prob >= self.threshold else 0


def _sigmoid(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, -60.0, 60.0)
    return 1.0 / (1.0 + np.exp(-x))


def _build_supervised_rows(
    ticks: list[TradeTick],
    *,
    lookback: int,
    forward_horizon: int,
    initial_cash: float,
    max_position: int,
) -> tuple[np.ndarray, np.ndarray]:
    state = FeatureState(
        lookback=lookback,
        initial_cash=initial_cash,
        max_position=max_position,
    )
    xs: list[np.ndarray] = []
    ys: list[float] = []
    prices = [t.price for t in ticks]

    cash = initial_cash
    position = 0
    for i, tick in enumerate(ticks):
        vec = state.update(tick, position=position, cash=cash)
        if vec is None:
            continue
        end = i + forward_horizon
        if end >= len(prices):
            break
        fwd = math.log(prices[end] / tick.price)
        label = 1.0 if fwd > 0.0 else 0.0
        xs.append(vec)
        ys.append(label)

    if not xs:
        raise ValueError("not enough ticks to build a training set")
    return np.vstack(xs), np.array(ys, dtype=np.float64).reshape(-1, 1)


def train_mlp(
    ticks: list[TradeTick],
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
) -> MLPModel:
    rng = np.random.default_rng(seed)
    x, y = _build_supervised_rows(
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

    return MLPModel(
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


def save_mlp(
    model: MLPModel,
    path: Path,
    *,
    extra_meta: dict[str, Any] | None = None,
) -> Path:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    meta: dict[str, Any] = {
        "lookback": model.lookback,
        "forward_horizon": model.forward_horizon,
        "threshold": model.threshold,
        "target_shares": model.target_shares,
        "initial_cash": model.initial_cash,
        "feature_dim": FEATURE_DIM,
        "hidden_dim": model.hidden_dim,
        "model_type": "mlp_v1",
    }
    if extra_meta:
        meta.update(extra_meta)
    np.savez(
        path,
        w1=model.w1,
        b1=model.b1,
        w2=model.w2,
        b2=model.b2,
        meta=json.dumps(meta),
    )
    return path


def load_mlp(path: Path) -> MLPModel:
    with np.load(path.resolve(), allow_pickle=False) as data:
        meta = json.loads(str(data["meta"]))
        return MLPModel(
            w1=data["w1"],
            b1=data["b1"],
            w2=data["w2"],
            b2=data["b2"],
            lookback=int(meta["lookback"]),
            forward_horizon=int(meta["forward_horizon"]),
            threshold=float(meta["threshold"]),
            target_shares=int(meta["target_shares"]),
            initial_cash=float(meta["initial_cash"]),
        )


def _sorted_ticks(ticks: list[TradeTick]) -> list[TradeTick]:
    return sorted(ticks, key=lambda t: (t.ts_event_ns, t.symbol))


def _min_ticks_for_training(*, lookback: int, forward_horizon: int) -> int:
    return lookback + forward_horizon + 2


def train_from_parquet(
    *,
    ticks_path: Path,
    out: Path,
    seed: int = 42,
    lookback: int = 20,
    forward_horizon: int = 5,
    hidden_dim: int = 8,
    epochs: int = 80,
    learning_rate: float = 0.05,
    threshold: float = 0.5,
    target_shares: int = 50,
    initial_cash: float = 1_000_000.0,
) -> MLPModel:
    path = ticks_path.resolve()
    ticks = _sorted_ticks(parquet_to_ticks(path))
    need = _min_ticks_for_training(lookback=lookback, forward_horizon=forward_horizon)
    if len(ticks) < need:
        raise ValueError(
            f"parquet has {len(ticks)} ticks; need at least {need} "
            f"(lookback={lookback}, forward_horizon={forward_horizon})"
        )
    model = train_mlp(
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
    save_mlp(
        model,
        out,
        extra_meta={
            "training_source": "parquet",
            "training_ticks_path": str(path),
            "training_tick_count": len(ticks),
            "training_symbol": ticks[0].symbol if ticks else None,
        },
    )
    return model
