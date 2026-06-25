"""Feature builder uses only past prices at each step."""

from __future__ import annotations

from morning_star.features.builder import FeatureState
from tick_fixtures import make_price_series_ticks


def test_feature_state_warms_up_before_emitting() -> None:
    ticks = make_price_series_ticks(n=25, step=0.1)
    state = FeatureState(lookback=20, initial_cash=1_000_000.0, max_position=10)
    outputs = [
        state.update(tick, position=0, cash=1_000_000.0)
        for tick in ticks
    ]
    assert outputs[:20] == [None] * 20
    assert outputs[20] is not None
    assert len(outputs[20]) == 5
