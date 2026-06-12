"""RSS entry mapping (no HTTP)."""

from __future__ import annotations

from time import struct_time

import feedparser

from crucibo.models import utc_now_ns
from crucibo.news.rss import (
    dedupe_events,
    entry_guid,
    filter_events_for_day,
    parse_feed_entries,
    rss_entry_to_news_event,
    struct_time_to_ns,
)

SAMPLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Fed holds rates steady</title>
      <link>https://example.com/fed-rates</link>
      <guid>fed-rates-1</guid>
      <pubDate>Wed, 11 Jun 2026 14:30:00 GMT</pubDate>
      <description>Policy statement released.</description>
      <author>Federal Reserve</author>
    </item>
    <item>
      <title>Older headline</title>
      <link>https://example.com/old</link>
      <guid>old-1</guid>
      <pubDate>Tue, 10 Jun 2026 09:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def test_struct_time_to_ns_utc() -> None:
    st = struct_time((2026, 6, 11, 14, 30, 0, 0, 0, 0))
    assert struct_time_to_ns(st) == 1_781_188_200_000_000_000


def test_rss_entry_maps_to_news_event() -> None:
    ingest = utc_now_ns()
    entry = {
        "title": "Apple beats estimates",
        "link": "https://example.com/aapl",
        "id": "abc-123",
        "published_parsed": struct_time((2026, 6, 11, 16, 0, 0, 0, 0, 0)),
        "summary": "Earnings beat.",
        "author": "Reuters",
    }
    event = rss_entry_to_news_event(entry, source="test", ts_ingest_ns=ingest)
    assert event is not None
    assert event.source == "test"
    assert event.guid == "abc-123"
    assert event.title == "Apple beats estimates"
    assert event.summary == "Earnings beat."
    assert event.author == "Reuters"
    assert event.ts_ingest_ns == ingest


def test_entry_guid_falls_back_to_link() -> None:
    assert entry_guid({"link": "https://example.com/x"}) == "https://example.com/x"


def test_parse_and_filter_by_day() -> None:
    ingest = utc_now_ns()
    parsed = feedparser.parse(SAMPLE_RSS)
    events = parse_feed_entries(parsed, source="fed-press", ts_ingest_ns=ingest)
    assert len(events) == 2
    on_day = filter_events_for_day(events, "2026-06-11")
    assert len(on_day) == 1
    assert on_day[0].title == "Fed holds rates steady"


def test_dedupe_events() -> None:
    ingest = utc_now_ns()
    base = {
        "title": "Dup",
        "link": "https://example.com/dup",
        "id": "same-guid",
        "published_parsed": struct_time((2026, 6, 11, 12, 0, 0, 0, 0, 0)),
    }
    first = rss_entry_to_news_event(base, source="x", ts_ingest_ns=ingest)
    second = rss_entry_to_news_event(base, source="x", ts_ingest_ns=ingest)
    assert first is not None and second is not None
    assert len(dedupe_events([first, second])) == 1
