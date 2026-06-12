"""RSS/Atom fetch → NewsEvent → silver Parquet."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import struct_time
from typing import Any

import feedparser
import httpx

from crucibo.io_parquet import news_to_parquet
from crucibo.models import NewsEvent, utc_now_ns
from crucibo.news.feeds import get_feed

USER_AGENT = "crucibo/0.1 (+https://github.com/sweet-little-adder/crucibo; research ingest)"


def struct_time_to_ns(st: struct_time) -> int:
    dt = datetime(st.tm_year, st.tm_mon, st.tm_mday, st.tm_hour, st.tm_min, st.tm_sec, tzinfo=UTC)
    return int(dt.timestamp() * 1_000_000_000)


def ns_to_day_utc(ns: int) -> str:
    return datetime.fromtimestamp(ns / 1_000_000_000, tz=UTC).strftime("%Y-%m-%d")


def entry_ts_event_ns(entry: dict[str, Any]) -> int | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(key)
        if parsed:
            return struct_time_to_ns(parsed)
    return None


def entry_guid(entry: dict[str, Any]) -> str:
    for key in ("id", "guid"):
        value = entry.get(key)
        if value:
            return str(value).strip()
    link = entry.get("link")
    if link:
        return str(link).strip()
    title = entry.get("title", "")
    return hashlib.sha256(f"{title}|{link}".encode()).hexdigest()


def entry_summary(entry: dict[str, Any]) -> str | None:
    for key in ("summary", "description", "subtitle"):
        value = entry.get(key)
        if value:
            text = str(value).strip()
            if text:
                return text
    return None


def entry_author(entry: dict[str, Any]) -> str | None:
    author = entry.get("author")
    if author:
        return str(author).strip()
    authors = entry.get("authors")
    if authors and isinstance(authors, list):
        names = [a.get("name") for a in authors if isinstance(a, dict) and a.get("name")]
        if names:
            return ", ".join(str(n) for n in names)
    return None


def rss_entry_to_news_event(
    entry: dict[str, Any],
    *,
    source: str,
    ts_ingest_ns: int,
) -> NewsEvent | None:
    ts_event = entry_ts_event_ns(entry)
    if ts_event is None:
        return None
    title = entry.get("title")
    link = entry.get("link")
    if not title or not link:
        return None
    return NewsEvent(
        ts_event_ns=ts_event,
        ts_ingest_ns=ts_ingest_ns,
        source=source,
        guid=entry_guid(entry),
        url=str(link).strip(),
        title=str(title).strip(),
        summary=entry_summary(entry),
        author=entry_author(entry),
        symbols=None,
    )


def fetch_rss_feed(client: httpx.Client, url: str) -> feedparser.FeedParserDict:
    response = client.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml"},
        follow_redirects=True,
    )
    response.raise_for_status()
    return feedparser.parse(response.content)


def filter_events_for_day(events: list[NewsEvent], day: str) -> list[NewsEvent]:
    return [event for event in events if ns_to_day_utc(event.ts_event_ns) == day]


def dedupe_events(events: list[NewsEvent]) -> list[NewsEvent]:
    seen: set[tuple[str, str]] = set()
    unique: list[NewsEvent] = []
    for event in sorted(events, key=lambda e: e.ts_event_ns):
        key = (event.source, event.guid)
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return unique


def parse_feed_entries(
    parsed: feedparser.FeedParserDict,
    *,
    source: str,
    ts_ingest_ns: int,
) -> list[NewsEvent]:
    events: list[NewsEvent] = []
    for entry in parsed.get("entries") or []:
        mapped = rss_entry_to_news_event(entry, source=source, ts_ingest_ns=ts_ingest_ns)
        if mapped is not None:
            events.append(mapped)
    return events


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class IngestOutcome:
    parquet_path: Path
    manifest_path: Path
    row_count: int


def ingest_rss_feed_day(
    *,
    day: str,
    source_id: str | None = None,
    feed_url: str | None = None,
    feed_name: str | None = None,
    silver_root: Path | None = None,
    git_commit: str | None = None,
) -> IngestOutcome:
    """Pull one feed/day → ``data/silver/news/source=S/date=D/articles.parquet``."""
    if feed_url:
        source = (source_id or "custom").strip().lower()
        name = feed_name or source
        url = feed_url
    elif source_id:
        spec = get_feed(source_id)
        source = spec.source_id
        name = spec.name
        url = spec.url
    else:
        raise ValueError("provide --source or --feed-url")

    if silver_root is None:
        silver_root = Path(os.environ.get("CRUCIBO_DATA_ROOT", "data"))

    slice_dir = silver_root / "silver" / "news" / f"source={source}" / f"date={day}"
    parquet_path = slice_dir / "articles.parquet"
    manifest_path = slice_dir / "manifest.json"

    ingest_ns = utc_now_ns()
    with httpx.Client(timeout=60.0) as client:
        parsed = fetch_rss_feed(client, url)

    events = filter_events_for_day(
        dedupe_events(parse_feed_entries(parsed, source=source, ts_ingest_ns=ingest_ns)),
        day,
    )

    news_to_parquet(events, parquet_path)

    pq_hash = _sha256(parquet_path) if events else None
    gh = git_commit
    if gh is None:
        gh = os.environ.get("CRUCIBO_GIT_SHA", "").strip() or None

    manifest = {
        "vendor": "rss",
        "source": source,
        "feed_name": name,
        "feed_url": url,
        "day_utc": day,
        "fetched_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "row_count": len(events),
        "parquet_path": str(parquet_path.resolve()),
        "parquet_sha256": pq_hash,
        "news_ts_ingest_ns_batch": ingest_ns,
        "git_sha": gh,
        "schema_version_news": 1,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return IngestOutcome(
        parquet_path=parquet_path,
        manifest_path=manifest_path,
        row_count=len(events),
    )


def ingest_all_feeds_day(
    *,
    day: str,
    silver_root: Path | None = None,
    git_commit: str | None = None,
) -> list[IngestOutcome]:
    from crucibo.news.feeds import DEFAULT_FEEDS

    outcomes: list[IngestOutcome] = []
    for feed in DEFAULT_FEEDS:
        outcomes.append(
            ingest_rss_feed_day(
                day=day,
                source_id=feed.source_id,
                silver_root=silver_root,
                git_commit=git_commit,
            )
        )
    return outcomes
