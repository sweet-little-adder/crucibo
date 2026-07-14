"""Recorded show build/load roundtrip."""

from __future__ import annotations

import json
from pathlib import Path

from bar_ticks import make_price_series_ticks
from crucibo.paper.engine import PaperConfig
from crucibo.paper.recording import (
    filter_ticks_by_day,
    load_show,
    record_strategy_session,
    save_show,
    tick_ny_date,
)
from crucibo.replay.strategies import BuyAndHold


def test_filter_ticks_by_day() -> None:
    ticks = make_price_series_ticks(n=2)
    day = tick_ny_date(ticks[0])
    picked = filter_ticks_by_day(ticks, day)
    assert len(picked) >= 1


def test_record_and_load_show(tmp_path: Path) -> None:
    ticks = make_price_series_ticks(n=5)
    cfg = PaperConfig(initial_cash=100_000.0, slip_bps=0.0, fee_per_share=0.0)
    recording = record_strategy_session(
        strategy=BuyAndHold(target_shares=10),
        ticks=ticks,
        cfg=cfg,
        feed="replay",
        interval="daily",
        strategy_name="buy_hold",
        model_path=None,
        show_day=tick_ny_date(ticks[0]),
    )
    out = tmp_path / "show.json"
    save_show(recording, out)
    loaded = load_show(out)
    assert loaded.schema_version == 1
    assert len(loaded.events) == 5
    assert loaded.session["mode"] == "show"
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["events"][0]["type"] == "tick"