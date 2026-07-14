"""Economics config and cost helpers."""

from __future__ import annotations

import pytest

from crucibo.backtest.economics import EconomicsConfig, fee_cash, slip_multiplier


def test_slip_multiplier_buy_sell() -> None:
    assert slip_multiplier(side="BUY", slip_bps=10.0) == pytest.approx(1.001)
    assert slip_multiplier(side="SELL", slip_bps=10.0) == pytest.approx(0.999)


def test_fee_cash() -> None:
    assert fee_cash(notional=10_000.0, fee_bps=4.0) == pytest.approx(4.0)


def test_economics_rejects_bad_latency() -> None:
    with pytest.raises(ValueError, match="latency_bars"):
        EconomicsConfig(latency_bars=2)