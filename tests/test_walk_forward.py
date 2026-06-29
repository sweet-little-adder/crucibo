"""Walk-forward date split tests."""

from __future__ import annotations

import pytest

from morning_star.train.split import split_ticks_by_date
from tick_fixtures import make_price_series_ticks


def test_split_ticks_by_date_no_overlap() -> None:
    ticks = make_price_series_ticks(n=10, dt_ns=86_400_000_000_000)
    # Assign synthetic calendar spread via ts_event_ns
    base = 1_704_067_200_000_000_000  # 2024-01-01 UTC
    spaced = []
    for i, tick in enumerate(ticks):
        spaced.append(tick.model_copy(update={"ts_event_ns": base + i * 86_400_000_000_000}))
    train, oos = split_ticks_by_date(spaced, train_end="2024-01-05", oos_start="2024-01-06")
    assert len(train) == 5
    assert len(oos) == 5


def test_split_rejects_overlapping_windows() -> None:
    ticks = make_price_series_ticks(n=3)
    with pytest.raises(ValueError, match="oos_start"):
        split_ticks_by_date(ticks, train_end="2024-01-10", oos_start="2024-01-10")
