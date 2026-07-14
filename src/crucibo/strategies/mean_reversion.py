"""Z-score mean reversion on bar closes."""

from __future__ import annotations

import math

from crucibo.core.bar import Bar
from crucibo.strategies.base import BarContext


class MeanReversionStrategy:
    def __init__(
        self,
        *,
        lookback: int = 20,
        entry_z: float = 1.0,
        target_shares: int = 100,
    ) -> None:
        if lookback < 2:
            raise ValueError("lookback must be >= 2")
        if entry_z <= 0:
            raise ValueError("entry_z must be > 0")
        self._lookback = lookback
        self._entry_z = entry_z
        self._target_shares = target_shares
        self._signals: list[int] = []

    def prepare(self, bars: list[Bar]) -> None:
        closes = [b.close for b in bars]
        self._signals = [0] * len(closes)
        for i in range(len(closes)):
            if i + 1 < self._lookback:
                continue
            window = closes[i + 1 - self._lookback : i + 1]
            mean = sum(window) / len(window)
            var = sum((x - mean) ** 2 for x in window) / len(window)
            z = (closes[i] - mean) / (math.sqrt(var) + 1e-12)
            if z <= -self._entry_z:
                self._signals[i] = self._target_shares
            elif z >= self._entry_z:
                self._signals[i] = 0
            else:
                self._signals[i] = self._signals[i - 1] if i > 0 else 0

    def on_bar(self, ctx: BarContext) -> int:
        return self._signals[ctx.index]