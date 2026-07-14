"""Strategy protocol for the event-driven backtest runner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from crucibo.backtest.portfolio import PortfolioView
from crucibo.core.bar import Bar


@dataclass(frozen=True)
class BarContext:
    bar: Bar
    index: int
    bars: tuple[Bar, ...]
    portfolio: PortfolioView


class Strategy(Protocol):
    """Targets absolute share count (long-only)."""

    def prepare(self, bars: list[Bar]) -> None: ...

    def on_bar(self, ctx: BarContext) -> int: ...