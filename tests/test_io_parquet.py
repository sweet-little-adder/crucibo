from pathlib import Path

from bar_ticks import make_price_series_ticks
from crucibo.io_parquet import parquet_to_ticks, read_ticks_parquet, ticks_to_parquet
from crucibo.models import TradeTick


def test_parquet_roundtrip(tmp_path: Path) -> None:
    ticks = make_price_series_ticks(symbol="AAPL", n=20, dt_ns=500_000_000)
    path = tmp_path / "slice.parquet"
    ticks_to_parquet(ticks, path)
    df = read_ticks_parquet(path)
    assert df.height == 20
    assert df["symbol"].unique().to_list() == ["AAPL"]


def test_parquet_empty_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "empty.parquet"
    ticks_to_parquet([], path)
    df = read_ticks_parquet(path)
    assert df.height == 0


def test_parquet_ticks_object_roundtrip(tmp_path: Path) -> None:
    ticks = [
        TradeTick(
            ts_event_ns=100,
            ts_ingest_ns=101,
            symbol="Z",
            price=1.5,
            size=10,
            conditions="1,2",
        )
    ]
    p = tmp_path / "t.parquet"
    ticks_to_parquet(ticks, p)
    assert parquet_to_ticks(p) == ticks
