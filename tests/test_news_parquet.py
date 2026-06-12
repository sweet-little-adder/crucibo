from pathlib import Path

from crucibo.io_parquet import news_to_parquet, parquet_to_news_events, read_news_parquet
from crucibo.models import NewsEvent


def test_news_parquet_roundtrip(tmp_path: Path) -> None:
    events = [
        NewsEvent(
            ts_event_ns=1_780_694_600_000_000_000,
            ts_ingest_ns=1_780_694_700_000_000_000,
            source="fed-press",
            guid="fed-1",
            url="https://example.com/fed",
            title="FOMC statement",
            summary="Rates unchanged.",
            author="Federal Reserve",
            symbols=None,
        )
    ]
    path = tmp_path / "articles.parquet"
    news_to_parquet(events, path)
    df = read_news_parquet(path)
    assert df.height == 1
    assert parquet_to_news_events(path) == events
