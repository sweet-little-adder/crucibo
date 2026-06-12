"""Free news ingest adapters (RSS / Atom)."""

from crucibo.news.feeds import list_feeds
from crucibo.news.rss import ingest_rss_feed_day

__all__ = ["ingest_rss_feed_day", "list_feeds"]
