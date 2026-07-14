"""Local account book for the live equities path (intended state)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Position:
    symbol: str
    shares: int = 0
    avg_price: float = 0.0

    @property
    def notional(self) -> float:
        return self.shares * self.avg_price


@dataclass
class LocalAccount:
    """Cash + positions we believe we hold after applying our own fills."""

    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    equity_peak: float = 0.0
    realized_pnl: float = 0.0

    def position_shares(self, symbol: str) -> int:
        pos = self.positions.get(symbol.upper())
        return pos.shares if pos else 0

    def mark_equity(self, marks: dict[str, float]) -> float:
        equity = self.cash
        for sym, pos in self.positions.items():
            px = marks.get(sym, pos.avg_price)
            equity += pos.shares * px
        self.equity_peak = max(self.equity_peak, equity)
        return equity

    def apply_fill(
        self,
        *,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        fee: float,
    ) -> None:
        sym = symbol.upper()
        if qty <= 0:
            raise ValueError("fill qty must be positive")
        pos = self.positions.get(sym) or Position(symbol=sym)
        if side.upper() == "BUY":
            total_cost = qty * price + fee
            if total_cost > self.cash + 1e-9:
                raise ValueError(
                    f"insufficient cash: need {total_cost:.2f} have {self.cash:.2f}"
                )
            new_shares = pos.shares + qty
            if new_shares > 0:
                pos.avg_price = (
                    (pos.shares * pos.avg_price + qty * price) / new_shares
                    if pos.shares > 0
                    else price
                )
            pos.shares = new_shares
            self.cash -= total_cost
        elif side.upper() == "SELL":
            if qty > pos.shares:
                raise ValueError(f"cannot sell {qty} > position {pos.shares}")
            proceeds = qty * price - fee
            self.realized_pnl += (price - pos.avg_price) * qty - fee
            pos.shares -= qty
            self.cash += proceeds
            if pos.shares == 0:
                pos.avg_price = 0.0
        else:
            raise ValueError(f"unknown side {side!r}")
        if pos.shares == 0:
            self.positions.pop(sym, None)
        else:
            self.positions[sym] = pos

    def snapshot(self, marks: dict[str, float] | None = None) -> dict[str, object]:
        marks = marks or {}
        positions = {
            sym: {"shares": p.shares, "avg_price": p.avg_price}
            for sym, p in self.positions.items()
        }
        return {
            "cash": self.cash,
            "positions": positions,
            "equity": self.mark_equity(marks),
            "equity_peak": self.equity_peak,
            "realized_pnl": self.realized_pnl,
        }
