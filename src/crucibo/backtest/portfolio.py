"""Portfolio state — cash, shares, equity marking."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Portfolio:
    cash: float
    shares: int = 0
    equity_peak: float = field(default=0.0)

    def __post_init__(self) -> None:
        self.equity_peak = max(self.equity_peak, self.cash)

    def equity_at(self, mark_price: float) -> float:
        return self.cash + self.shares * mark_price

    def update_peak(self, mark_price: float) -> float:
        eq = self.equity_at(mark_price)
        self.equity_peak = max(self.equity_peak, eq)
        return eq

    def drawdown(self, mark_price: float) -> float:
        return self.equity_peak - self.equity_at(mark_price)


@dataclass(frozen=True)
class PortfolioView:
    cash: float
    shares: int
    equity: float
    drawdown: float