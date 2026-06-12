"""Curated free RSS/Atom feeds for macro and market news."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeedSpec:
    source_id: str
    name: str
    url: str
    description: str


# Stable public feeds — verify ToS before production redistribution.
DEFAULT_FEEDS: tuple[FeedSpec, ...] = (
    FeedSpec(
        source_id="fed-press",
        name="Federal Reserve — all press releases",
        url="https://www.federalreserve.gov/feeds/press_all.xml",
        description="FOMC statements, speeches, regulatory press releases.",
    ),
    FeedSpec(
        source_id="sec-press",
        name="SEC — press releases",
        url="https://www.sec.gov/news/pressreleases.rss",
        description="US securities regulator announcements and enforcement.",
    ),
    FeedSpec(
        source_id="bbc-business",
        name="BBC News — business",
        url="https://feeds.bbci.co.uk/news/business/rss.xml",
        description="General business headlines (global macro context).",
    ),
    FeedSpec(
        source_id="marketwatch-top",
        name="MarketWatch — top stories",
        url="https://feeds.marketwatch.com/marketwatch/topstories/",
        description="US market-focused headlines.",
    ),
)

_FEEDS_BY_ID = {feed.source_id: feed for feed in DEFAULT_FEEDS}


def list_feeds() -> list[FeedSpec]:
    return list(DEFAULT_FEEDS)


def get_feed(source_id: str) -> FeedSpec:
    key = source_id.strip().lower()
    if key not in _FEEDS_BY_ID:
        known = ", ".join(sorted(_FEEDS_BY_ID))
        raise ValueError(f"unknown feed source {source_id!r}; known: {known}")
    return _FEEDS_BY_ID[key]
