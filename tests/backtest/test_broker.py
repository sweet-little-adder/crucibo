"""SimBroker fills, fees, and slippage."""

from __future__ import annotations

import pytest

from crucibo.backtest.broker import SimBroker
from crucibo.backtest.economics import EconomicsConfig, fee_cash, slip_multiplier
from crucibo.backtest.portfolio import Portfolio
from crucibo.core.bar import Bar
from crucibo.core.types import Vendor


def _bar(*, close: float, ts: int = 1_700_000_000_000_000_000) -> Bar:
    return Bar(
        ts_close_ns=ts,
        symbol="TST",
        interval="daily",
        vendor=Vendor.ALPHAVANTAGE,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=1_000.0,
    )


def test_buy_applies_slippage_and_fee() -> None:
    cfg = EconomicsConfig(initial_cash=100_000.0, fee_bps=4.0, slippage_bps=2.0)
    portfolio = Portfolio(cash=cfg.initial_cash)
    broker = SimBroker(cfg=cfg, portfolio=portfolio)
    bar = _bar(close=100.0)

    fill = broker.rebalance_to(bar=bar, target_shares=10, exec_price=bar.close, signal_bar_index=0)
    assert fill is not None
    assert fill.side == "BUY"
    assert fill.qty_shares == 10

    px = 100.0 * slip_multiplier(side="BUY", slip_bps=2.0)
    gross = 10 * px
    fee = fee_cash(notional=gross, fee_bps=4.0)
    assert fill.exec_price == pytest.approx(px)
    assert fill.fee_cash == pytest.approx(fee)
    assert portfolio.cash == pytest.approx(100_000.0 - gross - fee)
    assert portfolio.shares == 10


def test_sell_reduces_position() -> None:
    cfg = EconomicsConfig(initial_cash=100_000.0, fee_bps=0.0, slippage_bps=0.0)
    portfolio = Portfolio(cash=50_000.0, shares=20)
    broker = SimBroker(cfg=cfg, portfolio=portfolio)
    bar = _bar(close=50.0)

    fill = broker.rebalance_to(bar=bar, target_shares=0, exec_price=bar.close, signal_bar_index=1)
    assert fill is not None
    assert fill.side == "SELL"
    assert fill.qty_shares == 20
    assert portfolio.shares == 0
    assert portfolio.cash == pytest.approx(51_000.0)


def test_no_fill_when_already_at_target() -> None:
    cfg = EconomicsConfig()
    portfolio = Portfolio(cash=100_000.0, shares=10)
    broker = SimBroker(cfg=cfg, portfolio=portfolio)
    bar = _bar(close=100.0)

    assert broker.rebalance_to(bar=bar, target_shares=10, exec_price=bar.close, signal_bar_index=0) is None
    assert broker.fills == []