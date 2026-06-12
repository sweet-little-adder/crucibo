"""Alpha Vantage JSON → TradeTick (no HTTP)."""

from crucibo.alphavantage.bars import (
    daily_rows_to_ticks,
    intraday_rows_to_ticks,
    parse_av_daily_ts,
    parse_av_intraday_ts,
)
from crucibo.models import utc_now_ns


def test_parse_av_daily_ts() -> None:
    ns = parse_av_daily_ts("2025-06-03")
    assert ns > 0


def test_parse_av_intraday_ts() -> None:
    ns = parse_av_intraday_ts("2025-06-03 15:55:00")
    assert ns > 0


def test_daily_rows_to_ticks() -> None:
    ingest = utc_now_ns()
    rows = {
        "2025-06-02": {
            "1. open": "100.0",
            "2. high": "101.0",
            "3. low": "99.5",
            "4. close": "100.5",
            "5. volume": "1000000",
        },
        "2025-06-03": {
            "1. open": "100.5",
            "2. high": "102.0",
            "3. low": "100.0",
            "4. close": "101.5",
            "5. volume": "1200000",
        },
    }
    ticks = daily_rows_to_ticks(rows, symbol="AAPL", ts_ingest_ns=ingest)
    assert len(ticks) == 2
    assert ticks[0].symbol == "AAPL"
    assert ticks[0].price == 100.5
    assert ticks[0].conditions == "alphavantage:daily"
    assert ticks[1].price == 101.5


def test_intraday_rows_filter_day() -> None:
    ingest = utc_now_ns()
    rows = {
        "2025-06-03 15:55:00": {
            "1. open": "100.0",
            "2. high": "100.2",
            "3. low": "99.9",
            "4. close": "100.1",
            "5. volume": "5000",
        },
        "2025-06-04 15:55:00": {
            "1. open": "100.1",
            "2. high": "100.3",
            "3. low": "100.0",
            "4. close": "100.2",
            "5. volume": "6000",
        },
    }
    ticks = intraday_rows_to_ticks(
        rows,
        symbol="AAPL",
        interval="5min",
        ts_ingest_ns=ingest,
        day="2025-06-03",
    )
    assert len(ticks) == 1
    assert ticks[0].conditions == "alphavantage:intraday-5min"
