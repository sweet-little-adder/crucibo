"""Polygon JSON → TradeTick (no HTTP)."""

import pytest

from crucibo.models import utc_now_ns
from crucibo.polygon.trades import polygon_trade_result_to_tick


def test_polygon_row_maps_to_tick() -> None:
    ingest = utc_now_ns()
    row = {
        "participant_timestamp": 1_704_067_800_012_345_678,
        "sip_timestamp": 1_704_067_800_099_999_999,
        "price": 192.455,
        "size": 100,
        "conditions": [12, 37],
        "exchange": 11,
        "id": "abc123",
    }
    t = polygon_trade_result_to_tick(row, symbol="AAPL", ts_ingest_ns=ingest)
    assert t.symbol == "AAPL"
    assert t.ts_event_ns == row["participant_timestamp"]
    assert t.ts_ingest_ns == ingest
    assert pytest.approx(t.price) == row["price"]
    assert t.size == 100
    assert t.conditions == "12,37"


def test_polygon_row_falls_back_to_sip_timestamp() -> None:
    ingest = utc_now_ns()
    row = {
        "sip_timestamp": 1_704_067_801_000_000_000,
        "price": 50.0,
        "size": 10,
    }
    t = polygon_trade_result_to_tick(row, symbol="XOM", ts_ingest_ns=ingest)
    assert t.ts_event_ns == row["sip_timestamp"]
