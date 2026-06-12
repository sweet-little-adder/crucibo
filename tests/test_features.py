"""Feature builder tests."""

from __future__ import annotations

from crucibo.features import FEATURE_DIM, FeatureState
from crucibo.models import TradeTick


def _tick(i: int, price: float) -> TradeTick:
    ts = 1_700_000_000_000_000_000 + i * 1_000_000
    return TradeTick(
        ts_event_ns=ts,
        ts_ingest_ns=ts,
        symbol="TST",
        price=price,
        size=10,
    )


def test_feature_warmup_then_vector() -> None:
    state = FeatureState(lookback=3, initial_cash=1000.0, max_position=10)
    assert state.update(_tick(0, 100.0), position=0, cash=1000.0) is None
    assert state.update(_tick(1, 101.0), position=0, cash=1000.0) is None
    assert state.update(_tick(2, 102.0), position=0, cash=1000.0) is None
    vec = state.update(_tick(3, 103.0), position=2, cash=900.0)
    assert vec is not None
    assert vec.shape == (FEATURE_DIM,)


def test_features_use_only_past_prices() -> None:
    state = FeatureState(lookback=2, initial_cash=1000.0, max_position=5)
    for i, px in enumerate([10.0, 10.5, 10.2, 10.8]):
        vec = state.update(_tick(i, px), position=0, cash=1000.0)
    assert vec is not None
    assert vec[3] == 0.0
    assert vec[4] == 1.0
