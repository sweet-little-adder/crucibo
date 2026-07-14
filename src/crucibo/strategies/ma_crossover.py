"""Simple moving-average crossover on bar closes."""

from __future__ import annotations

from crucibo.core.bar import Bar
from crucibo.strategies.base import BarContext


class MaCrossoverStrategy:
    def __init__(self, *, fast: int = 12, slow: int = 26, target_shares: int = 100) -> None:
        if fast < 1 or slow < 1:
            raise ValueError("fast and slow must be >= 1")
        if fast >= slow:
            raise ValueError("fast period must be < slow period")
        if target_shares < 0:
            raise ValueError("target_shares must be >= 0")
        self._fast = fast
        self._slow = slow
        self._target_shares = target_shares
        self._signals: list[int] = []

    def prepare(self, bars: list[Bar]) -> None:
        closes = [b.close for b in bars]
        self._signals = [0] * len(closes)
        for i in range(len(closes)):
            if i + 1 < self._slow:
                continue
            fast_ma = sum(closes[i + 1 - self._fast : i + 1]) / self._fast
            slow_ma = sum(closes[i + 1 - self._slow : i + 1]) / self._slow
            self._signals[i] = self._target_shares if fast_ma > slow_ma else 0

    def on_bar(self, ctx: BarContext) -> int:
        return self._signals[ctx.index]