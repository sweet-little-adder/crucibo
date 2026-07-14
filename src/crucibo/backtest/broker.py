"""Simulated order execution with fees and slippage."""

from __future__ import annotations

from dataclasses import dataclass

from crucibo.backtest.economics import EconomicsConfig, fee_cash, slip_multiplier
from crucibo.backtest.portfolio import Portfolio
from crucibo.core.bar import Bar


@dataclass(frozen=True)
class Fill:
    ts_close_ns: int
    symbol: str
    side: str
    qty_shares: int
    exec_price: float
    fee_cash: float
    notional: float
    cash_after: float
    shares_after: int
    signal_bar_index: int

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "ts_event_ns": self.ts_close_ns,
            "symbol": self.symbol,
            "side": self.side,
            "qty_shares": self.qty_shares,
            "exec_price": self.exec_price,
            "fee_cash": self.fee_cash,
            "notional": self.notional,
            "cash_after": self.cash_after,
            "shares_after": self.shares_after,
            "signal_bar_index": self.signal_bar_index,
        }


class SimBroker:
    def __init__(self, *, cfg: EconomicsConfig, portfolio: Portfolio) -> None:
        self._cfg = cfg
        self._portfolio = portfolio
        self.fills: list[Fill] = []

    @property
    def portfolio(self) -> Portfolio:
        return self._portfolio

    def rebalance_to(
        self,
        *,
        bar: Bar,
        target_shares: int,
        exec_price: float,
        signal_bar_index: int,
    ) -> Fill | None:
        if target_shares < 0:
            raise ValueError("short selling not supported in v2 broker")
        if self._cfg.max_position_shares is not None:
            target_shares = min(target_shares, self._cfg.max_position_shares)

        delta = target_shares - self._portfolio.shares
        if delta == 0:
            return None

        if delta > 0:
            side = "BUY"
            px = exec_price * slip_multiplier(side=side, slip_bps=self._cfg.slippage_bps)
            gross = delta * px
            fee = fee_cash(notional=gross, fee_bps=self._cfg.fee_bps)
            total = gross + fee
            if total > self._portfolio.cash + 1e-9:
                raise ValueError(
                    f"insufficient cash: need {total:.2f} have {self._portfolio.cash:.2f}"
                )
            self._portfolio.cash -= total
            self._portfolio.shares += delta
            notional = gross
        else:
            qty = -delta
            side = "SELL"
            px = exec_price * slip_multiplier(side=side, slip_bps=self._cfg.slippage_bps)
            gross = qty * px
            fee = fee_cash(notional=gross, fee_bps=self._cfg.fee_bps)
            self._portfolio.cash += gross - fee
            self._portfolio.shares -= qty
            notional = gross

        fill = Fill(
            ts_close_ns=bar.ts_close_ns,
            symbol=bar.symbol,
            side=side,
            qty_shares=abs(delta),
            exec_price=px,
            fee_cash=fee,
            notional=notional,
            cash_after=self._portfolio.cash,
            shares_after=self._portfolio.shares,
            signal_bar_index=signal_bar_index,
        )
        self.fills.append(fill)
        return fill