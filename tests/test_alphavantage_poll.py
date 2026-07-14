"""Alpha Vantage paper poll helpers."""

from __future__ import annotations

from bar_ticks import make_price_series_ticks
from crucibo.paper.alphavantage_poll import seed_seen_bars, select_new_ticks


def test_seed_seen_bars_marks_history() -> None:
    ticks = make_price_series_ticks(n=3)
    seen = seed_seen_bars(ticks)
    assert len(seen) == 3


def test_select_new_ticks_only_returns_unseen() -> None:
    ticks = make_price_series_ticks(n=3)
    seen = seed_seen_bars(ticks[:2])
    fresh = select_new_ticks(seen=seen, ticks=ticks)
    assert len(fresh) == 1
    assert fresh[0].ts_event_ns == ticks[2].ts_event_ns