"""Supervised rows from tick history — labels use future bars only at train time."""

from __future__ import annotations

import math

import numpy as np

from morning_star.features.builder import FeatureState
from morning_star.ticks import Tick


def build_supervised_rows(
    ticks: list[Tick],
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


def min_ticks_for_training(*, lookback: int, forward_horizon: int) -> int:
    return lookback + forward_horizon + 2
