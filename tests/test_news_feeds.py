from crucibo.news.feeds import get_feed, list_feeds


def test_list_feeds_non_empty() -> None:
    feeds = list_feeds()
    assert len(feeds) >= 4
    ids = {feed.source_id for feed in feeds}
    assert "fed-press" in ids
    assert "sec-press" in ids


def test_get_feed_unknown_raises() -> None:
    try:
        get_feed("not-a-real-feed")
    except ValueError as exc:
        assert "unknown feed source" in str(exc)
    else:
        raise AssertionError("expected ValueError")
