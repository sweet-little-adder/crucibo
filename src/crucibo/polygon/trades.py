"""Historical stock trades via ``GET /v3/trades/{ticker}``."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from crucibo.io_parquet import ticks_to_parquet
from crucibo.models import TradeTick, utc_now_ns
from crucibo.settings import polygon_api_key

POLYGON_BASE = "https://api.polygon.io"


def _polygon_raise_for_status(resp: httpx.Response, *, what: str) -> None:
    """Turn HTTP errors into a message that includes Polygon's JSON/text body."""
    if resp.status_code < 400:
        return
    snippet = ""
    try:
        blob = resp.json()
        snippet = blob.get("message") or blob.get("error") or json.dumps(blob)[:900]
    except Exception:
        snippet = (resp.text or "").strip()[:900]

    plan_hint = ""
    if resp.status_code == 403:
        plan_hint = (
            " — Most often: `/v3/trades` historical ticks are not enabled on your "
            "Polygon/Massive plan (upgrade the Stocks product that includes trades/ticks)."
        )

    raise RuntimeError(
        f"Polygon HTTP {resp.status_code} {what}.{plan_hint}"
        + (f" Body: {snippet}" if snippet else "")
    )


def polygon_trade_result_to_tick(
    row: dict[str, Any],
    *,
    symbol: str,
    ts_ingest_ns: int,
) -> TradeTick:
    """Map one Polygon ``results[]`` object → :class:`~crucibo.models.TradeTick`."""
    participant = row.get("participant_timestamp")
    sip = row.get("sip_timestamp")
    ts_event = participant if participant is not None else sip
    if ts_event is None:
        raise ValueError(f"trade row missing timestamps: keys={sorted(row)!r}")
    conds = row.get("conditions")
    if isinstance(conds, list):
        conditions = ",".join(str(c) for c in conds) if conds else None
    else:
        conditions = None

    price = row.get("price")
    size = row.get("size")
    if price is None or size is None:
        raise ValueError(f"trade row missing price/size: keys={sorted(row)!r}")

    return TradeTick(
        ts_event_ns=int(ts_event),
        ts_ingest_ns=ts_ingest_ns,
        symbol=symbol,
        price=float(price),
        size=int(size),
        conditions=conditions,
    )


def _ensure_api_key_on_url(url: str, api_key: str) -> str:
    if "apiKey=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}apiKey={api_key}"


def _resolve_next_url(next_url: str) -> str:
    if next_url.startswith("http"):
        return next_url
    return urljoin(f"{POLYGON_BASE}/", next_url.lstrip("/"))


def iter_polygon_trade_pages(
    client: httpx.Client,
    *,
    api_key: str,
    ticker: str,
    timestamp_gte: str,
    timestamp_lte: str,
    limit: int = 50_000,
    sort: str = "timestamp",
    order: str = "asc",
) -> Iterator[list[dict[str, Any]]]:
    """Yield each page ``results`` list from Polygon (may be empty lists)."""

    url = f"{POLYGON_BASE}/v3/trades/{ticker}"
    params: dict[str, str | int] = {
        "apiKey": api_key,
        "timestamp.gte": timestamp_gte,
        "timestamp.lte": timestamp_lte,
        "limit": limit,
        "sort": sort,
        "order": order,
    }
    resp = client.get(url, params=params)
    _polygon_raise_for_status(resp, what=f"GET {url}")
    payload = resp.json()
    yield list(payload.get("results") or [])

    next_url = payload.get("next_url")
    while next_url:
        resolved = _ensure_api_key_on_url(_resolve_next_url(next_url), api_key)
        nxt = client.get(resolved)
        _polygon_raise_for_status(nxt, what="paged GET trades")
        page = nxt.json()
        yield list(page.get("results") or [])
        next_url = page.get("next_url")


def fetch_polygon_trades_day(
    client: httpx.Client,
    *,
    api_key: str,
    ticker: str,
    day: str,
) -> list[TradeTick]:
    """All ticks for UTC calendar ``day`` (``YYYY-MM-DD``) mapped to ticks.

    Uses participant timestamp where present, else SIP.
    """

    ingest_ns = utc_now_ns()
    sym = ticker.upper()
    ticks: list[TradeTick] = []
    for batch in iter_polygon_trade_pages(
        client,
        api_key=api_key,
        ticker=sym,
        timestamp_gte=day,
        timestamp_lte=day,
    ):
        for row in batch:
            ticks.append(
                polygon_trade_result_to_tick(row, symbol=sym, ts_ingest_ns=ingest_ns)
            )
    return ticks


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class IngestOutcome:
    parquet_path: Path
    manifest_path: Path
    row_count: int


def ingest_polygon_trades_day(
    *,
    symbol: str,
    day: str,
    silver_root: Path | None = None,
    git_commit: str | None = None,
) -> IngestOutcome:
    """Pull one symbol/day → ``data/silver/polygon/symbol=T/date=D/``.

    Respect ``CRUCIBO_DATA_ROOT`` env to override silver parent (defaults to repo ``data``).
    """
    api_key = polygon_api_key()
    sym = symbol.upper()
    if silver_root is None:
        silver_root = Path(os.environ.get("CRUCIBO_DATA_ROOT", "data"))

    slice_dir = silver_root / "silver" / "polygon" / f"symbol={sym}" / f"date={day}"
    parquet_path = slice_dir / "trades.parquet"
    manifest_path = slice_dir / "manifest.json"

    with httpx.Client(timeout=120.0) as client:
        ticks = fetch_polygon_trades_day(client, api_key=api_key, ticker=sym, day=day)

    ingest_batch_ns = ticks[0].ts_ingest_ns if ticks else utc_now_ns()

    ticks_to_parquet(ticks, parquet_path)

    pq_hash = _sha256(parquet_path) if ticks else None
    gh = git_commit
    if gh is None:
        gh = os.environ.get("CRUCIBO_GIT_SHA", "").strip() or None

    manifest = {
        "vendor": "polygon",
        "endpoint": "v3/trades",
        "symbol": sym,
        "day_utc": day,
        "fetched_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "row_count": len(ticks),
        "parquet_path": str(parquet_path.resolve()),
        "parquet_sha256": pq_hash,
        "tick_ts_ingest_ns_batch": ingest_batch_ns,
        "git_sha": gh,
        "schema_version_tick": 1,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return IngestOutcome(
        parquet_path=parquet_path,
        manifest_path=manifest_path,
        row_count=len(ticks),
    )