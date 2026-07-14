"""Binance JSON → TradeTick (no HTTP)."""

from crucibo.binance.klines import (
    binance_event_ns,
    funding_row_to_tick,
    kline_row_to_tick,
    klines_to_ticks,
    mark_kline_row_to_tick,
    merge_ticks_deterministic,
    parse_start_date_ms,
)
from crucibo.models import utc_now_ns


def _sample_kline(*, close_time_ms: int, close: str = "42000.0", volume: str = "123.45") -> list:
    return [
        close_time_ms - 299_999,
        "41900.0",
        "42100.0",
        "41800.0",
        close,
        volume,
        close_time_ms,
        "5000000.0",
        1000,
        "60.0",
        "2500000.0",
        "0",
    ]


def test_parse_start_date_ms() -> None:
    assert parse_start_date_ms("2024-01-01") == 1_704_067_200_000


def test_kline_row_to_tick() -> None:
    ingest = utc_now_ns()
    close_ms = 1_704_067_499_999
    tick = kline_row_to_tick(
        _sample_kline(close_time_ms=close_ms),
        symbol="btcusdt",
        interval="5m",
        ts_ingest_ns=ingest,
    )
    assert tick.symbol == "BTCUSDT"
    assert tick.price == 42000.0
    assert tick.size == 123
    assert tick.conditions == "binance:futures-5m"
    assert tick.ts_event_ns == binance_event_ns(close_ms, offset_ns=0)
    assert tick.ts_ingest_ns == ingest


def test_mark_kline_row_to_tick() -> None:
    ingest = utc_now_ns()
    close_ms = 1_704_067_499_999
    tick = mark_kline_row_to_tick(
        _sample_kline(close_time_ms=close_ms, close="41950.5"),
        symbol="BTCUSDT",
        interval="5m",
        ts_ingest_ns=ingest,
    )
    assert tick.price == 41950.5
    assert tick.conditions == "binance:mark-price-5m"
    assert tick.ts_event_ns == binance_event_ns(close_ms, offset_ns=1)


def test_funding_row_to_tick() -> None:
    ingest = utc_now_ns()
    funding_ms = 1_704_067_200_000
    tick = funding_row_to_tick(
        {"symbol": "BTCUSDT", "fundingTime": funding_ms, "fundingRate": "0.00010000"},
        symbol="BTCUSDT",
        ts_ingest_ns=ingest,
    )
    assert tick.price == 0.0001
    assert tick.conditions == "binance:funding-rate"
    assert tick.ts_event_ns == binance_event_ns(funding_ms, offset_ns=2)


def test_funding_row_to_tick_negative_rate() -> None:
    ingest = utc_now_ns()
    funding_ms = 1_704_067_200_000
    tick = funding_row_to_tick(
        {"symbol": "BTCUSDT", "fundingTime": funding_ms, "fundingRate": "-0.00000544"},
        symbol="BTCUSDT",
        ts_ingest_ns=ingest,
    )
    assert tick.price == -5.44e-06


def test_merge_ticks_deterministic_ordering() -> None:
    ingest = utc_now_ns()
    close_ms = 1_704_067_499_999
    kline = kline_row_to_tick(
        _sample_kline(close_time_ms=close_ms),
        symbol="BTCUSDT",
        interval="5m",
        ts_ingest_ns=ingest,
    )
    mark = mark_kline_row_to_tick(
        _sample_kline(close_time_ms=close_ms, close="41950.5"),
        symbol="BTCUSDT",
        interval="5m",
        ts_ingest_ns=ingest,
    )
    funding = funding_row_to_tick(
        {"symbol": "BTCUSDT", "fundingTime": close_ms, "fundingRate": "0.0001"},
        symbol="BTCUSDT",
        ts_ingest_ns=ingest,
    )
    merged = merge_ticks_deterministic([funding, mark, kline])
    assert [t.conditions for t in merged] == [
        "binance:futures-5m",
        "binance:mark-price-5m",
        "binance:funding-rate",
    ]


def test_klines_to_ticks_volume_floor() -> None:
    ingest = utc_now_ns()
    row = _sample_kline(close_time_ms=1_704_067_499_999, volume="0")
    ticks = klines_to_ticks([row], symbol="BTCUSDT", interval="5m", ts_ingest_ns=ingest)
    assert ticks[0].size == 1
