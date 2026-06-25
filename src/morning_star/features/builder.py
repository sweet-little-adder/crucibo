"""Causal streaming features — past ticks only, no lookahead."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from morning_star.ticks import Tick


@dataclass
class FeatureState:
    lookback: int = 20
    initial_cash: float = 1_000_000.0
    max_position: int = 100

    _prices: list[float] = field(default_factory=list)

    def reset(self) -> None:
        self._prices.clear()

    def update(
        self,
        tick: Tick,
        *,
        position: int,
        cash: float,
    ) -> np.ndarray | None:
        self._prices.append(tick.price)
        if len(self._prices) < self.lookback + 1:
            return None

        window = self._prices[-(self.lookback + 1) :]
        rets = [math.log(window[i] / window[i - 1]) for i in range(1, len(window))]
        ret_1 = rets[-1]
        mean_ret = sum(rets) / len(rets)

        sma = sum(window[1:]) / len(window[1:])
        var = sum((p - sma) ** 2 for p in window[1:]) / len(window[1:])
        price_z = (tick.price - sma) / (math.sqrt(var) + 1e-9)

        pos_cap = max(1, self.max_position)
        position_norm = position / pos_cap
        cash_norm = cash / self.initial_cash

        return np.array(
            [ret_1, mean_ret, price_z, position_norm, cash_norm],
            dtype=np.float64,
        )
