"""Binance kline payload mapping tests."""

from __future__ import annotations

from crucibo.paper.binance_ws import closed_kline_to_tick, kline_stream_url


def test_kline_stream_url() -> None:
    assert "btcusdt@kline_5m" in kline_stream_url(symbol="BTCUSDT", interval="5m")


def test_closed_kline_to_tick_ignores_open_candle() -> None:
    assert closed_kline_to_tick({"e": "kline", "k": {"x": False}}) is None


def test_closed_kline_to_tick_maps_fields() -> None:
    tick = closed_kline_to_tick(
        {
            "e": "kline",
            "k": {
                "x": True,
                "T": 1_700_000_300_000,
                "s": "BTCUSDT",
                "c": "42000.5",
                "v": "12.34",
                "i": "5m",
            },
        }
    )
    assert tick is not None
    assert tick.symbol == "BTCUSDT"
    assert tick.price == 42000.5
    assert tick.ts_event_ns == 1_700_000_300_000_000_000
