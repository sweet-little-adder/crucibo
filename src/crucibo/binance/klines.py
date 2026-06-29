"""Binance USD-M perpetual futures klines → TradeTick silver slices (public API)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from crucibo.io_parquet import ticks_to_parquet
from crucibo.models import TradeTick, utc_now_ns

BINANCE_FUTURES_BASE = "https://fapi.binance.com"

VALID_INTERVALS = (
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
    "1M",
)

# Nanosecond offsets within one exchange millisecond bucket for deterministic ordering.
KLINE_EVENT_OFFSET_NS = 0
MARK_PRICE_EVENT_OFFSET_NS = 1
FUNDING_EVENT_OFFSET_NS = 2

KLINES_PAGE_LIMIT = 1500
FUNDING_PAGE_LIMIT = 1000


def _raise_for_binance_payload(payload: Any, *, what: str) -> None:
    if isinstance(payload, dict) and "code" in payload:
        code = payload.get("code")
        msg = payload.get("msg", "")
        raise RuntimeError(f"Binance error ({what}): [{code}] {msg}")


def parse_start_date_ms(day: str) -> int:
    """UTC calendar day ``YYYY-MM-DD`` → epoch ms at 00:00:00 UTC."""
    dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)


def parse_end_date_ms(day: str) -> int:
    """UTC calendar day ``YYYY-MM-DD`` → epoch ms at 23:59:59.999 UTC."""
    dt = datetime.strptime(day, "%Y-%m-%d").replace(
        hour=23,
        minute=59,
        second=59,
        microsecond=999_000,
        tzinfo=UTC,
    )
    return int(dt.timestamp() * 1000)


def binance_event_ns(time_ms: int, *, offset_ns: int) -> int:
    """Map Binance millisecond timestamp → ``ts_event_ns`` with stable sub-ms offset."""
    return time_ms * 1_000_000 + offset_ns


def kline_row_to_tick(
    row: list[Any],
    *,
    symbol: str,
    interval: str,
    ts_ingest_ns: int,
) -> TradeTick:
    """Map one Binance kline array → :class:`~crucibo.models.TradeTick` (bar close)."""
    if len(row) < 7:
        raise ValueError(f"binance kline row too short: len={len(row)!r}")
    close_time_ms = int(row[6])
    close = float(row[4])
    volume = int(float(row[5]))
    return TradeTick(
        ts_event_ns=binance_event_ns(close_time_ms, offset_ns=KLINE_EVENT_OFFSET_NS),
        ts_ingest_ns=ts_ingest_ns,
        symbol=symbol.upper(),
        price=close,
        size=max(volume, 1),
        conditions=f"binance:futures-{interval}",
    )


def mark_kline_row_to_tick(
    row: list[Any],
    *,
    symbol: str,
    interval: str,
    ts_ingest_ns: int,
) -> TradeTick:
    """Map one Binance mark-price kline → tick at bar close (``price`` = mark)."""
    if len(row) < 7:
        raise ValueError(f"binance mark kline row too short: len={len(row)!r}")
    close_time_ms = int(row[6])
    mark = float(row[4])
    return TradeTick(
        ts_event_ns=binance_event_ns(close_time_ms, offset_ns=MARK_PRICE_EVENT_OFFSET_NS),
        ts_ingest_ns=ts_ingest_ns,
        symbol=symbol.upper(),
        price=mark,
        size=1,
        conditions=f"binance:mark-price-{interval}",
    )


def funding_row_to_tick(
    row: dict[str, Any],
    *,
    symbol: str,
    ts_ingest_ns: int,
) -> TradeTick:
    """Map one funding-rate record → tick (``price`` holds the rate as a float)."""
    funding_time_ms = row.get("fundingTime")
    funding_rate = row.get("fundingRate")
    if funding_time_ms is None or funding_rate is None:
        raise ValueError(f"funding row missing fields: keys={sorted(row)!r}")
    return TradeTick(
        ts_event_ns=binance_event_ns(int(funding_time_ms), offset_ns=FUNDING_EVENT_OFFSET_NS),
        ts_ingest_ns=ts_ingest_ns,
        symbol=symbol.upper(),
        price=float(funding_rate),
        size=1,
        conditions="binance:funding-rate",
    )


def klines_to_ticks(
    rows: list[list[Any]],
    *,
    symbol: str,
    interval: str,
    ts_ingest_ns: int,
) -> list[TradeTick]:
    ticks: list[TradeTick] = []
    for row in rows:
        ticks.append(
            kline_row_to_tick(row, symbol=symbol, interval=interval, ts_ingest_ns=ts_ingest_ns)
        )
    return ticks


def mark_klines_to_ticks(
    rows: list[list[Any]],
    *,
    symbol: str,
    interval: str,
    ts_ingest_ns: int,
) -> list[TradeTick]:
    ticks: list[TradeTick] = []
    for row in rows:
        ticks.append(
            mark_kline_row_to_tick(row, symbol=symbol, interval=interval, ts_ingest_ns=ts_ingest_ns)
        )
    return ticks


def funding_rows_to_ticks(
    rows: list[dict[str, Any]],
    *,
    symbol: str,
    ts_ingest_ns: int,
) -> list[TradeTick]:
    ticks: list[TradeTick] = []
    for row in rows:
        ticks.append(funding_row_to_tick(row, symbol=symbol, ts_ingest_ns=ts_ingest_ns))
    return ticks


def merge_ticks_deterministic(*streams: list[TradeTick]) -> list[TradeTick]:
    """Merge multiple tick streams sorted by ``(ts_event_ns, conditions)``."""
    merged: list[TradeTick] = []
    for stream in streams:
        merged.extend(stream)
    return sorted(merged, key=lambda t: (t.ts_event_ns, t.conditions or ""))


def iter_paginated_klines(
    client: httpx.Client,
    *,
    endpoint: str,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    limit: int = KLINES_PAGE_LIMIT,
    pause_s: float = 0.05,
) -> Iterator[list[list[Any]]]:
    """Yield kline pages from ``/fapi/v1/klines`` or ``/fapi/v1/markPriceKlines``."""
    url = f"{BINANCE_FUTURES_BASE}{endpoint}"
    cursor = start_ms
    while cursor <= end_ms:
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "startTime": cursor,
            "endTime": end_ms,
            "limit": limit,
        }
        response = client.get(url, params=params, timeout=60.0)
        response.raise_for_status()
        payload = response.json()
        _raise_for_binance_payload(payload, what=endpoint)
        if not isinstance(payload, list):
            raise RuntimeError(f"Binance {endpoint} expected list, got {type(payload)!r}")
        if not payload:
            break
        yield payload
        last_close_ms = int(payload[-1][6])
        next_cursor = last_close_ms + 1
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if pause_s > 0:
            time.sleep(pause_s)


def iter_paginated_funding_rates(
    client: httpx.Client,
    *,
    symbol: str,
    start_ms: int,
    end_ms: int,
    limit: int = FUNDING_PAGE_LIMIT,
    pause_s: float = 0.05,
) -> Iterator[list[dict[str, Any]]]:
    """Yield funding-rate pages from ``/fapi/v1/fundingRate``."""
    url = f"{BINANCE_FUTURES_BASE}/fapi/v1/fundingRate"
    cursor = start_ms
    while cursor <= end_ms:
        params = {
            "symbol": symbol.upper(),
            "startTime": cursor,
            "endTime": end_ms,
            "limit": limit,
        }
        response = client.get(url, params=params, timeout=60.0)
        response.raise_for_status()
        payload = response.json()
        _raise_for_binance_payload(payload, what="fundingRate")
        if not isinstance(payload, list):
            raise RuntimeError(f"Binance fundingRate expected list, got {type(payload)!r}")
        if not payload:
            break
        yield payload
        last_time_ms = int(payload[-1]["fundingTime"])
        next_cursor = last_time_ms + 1
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if pause_s > 0:
            time.sleep(pause_s)


def fetch_futures_klines(
    client: httpx.Client,
    *,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    ts_ingest_ns: int,
    include_mark_price: bool = True,
    include_funding: bool = True,
    pause_s: float = 0.05,
) -> list[TradeTick]:
    """Download klines plus optional mark-price klines and funding rates."""
    if interval not in VALID_INTERVALS:
        raise ValueError(f"interval must be one of {VALID_INTERVALS}, got {interval!r}")

    sym = symbol.upper()
    kline_rows: list[list[Any]] = []
    for page in iter_paginated_klines(
        client,
        endpoint="/fapi/v1/klines",
        symbol=sym,
        interval=interval,
        start_ms=start_ms,
        end_ms=end_ms,
        pause_s=pause_s,
    ):
        kline_rows.extend(page)

    kline_ticks = klines_to_ticks(
        kline_rows,
        symbol=sym,
        interval=interval,
        ts_ingest_ns=ts_ingest_ns,
    )

    mark_ticks: list[TradeTick] = []
    if include_mark_price:
        mark_rows: list[list[Any]] = []
        for page in iter_paginated_klines(
            client,
            endpoint="/fapi/v1/markPriceKlines",
            symbol=sym,
            interval=interval,
            start_ms=start_ms,
            end_ms=end_ms,
            pause_s=pause_s,
        ):
            mark_rows.extend(page)
        mark_ticks = mark_klines_to_ticks(
            mark_rows,
            symbol=sym,
            interval=interval,
            ts_ingest_ns=ts_ingest_ns,
        )

    funding_ticks: list[TradeTick] = []
    if include_funding:
        funding_rows: list[dict[str, Any]] = []
        for page in iter_paginated_funding_rates(
            client,
            symbol=sym,
            start_ms=start_ms,
            end_ms=end_ms,
            pause_s=pause_s,
        ):
            funding_rows.extend(page)
        funding_ticks = funding_rows_to_ticks(funding_rows, symbol=sym, ts_ingest_ns=ts_ingest_ns)

    return merge_ticks_deterministic(kline_ticks, mark_ticks, funding_ticks)


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
    kline_count: int
    mark_price_count: int
    funding_count: int


def _write_manifest(*, manifest_path: Path, manifest: dict[str, Any]) -> None:
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def ingest_binance_futures(
    *,
    symbol: str,
    interval: str,
    start_date: str,
    end_date: str | None = None,
    silver_root: Path | None = None,
    git_commit: str | None = None,
    include_mark_price: bool = True,
    include_funding: bool = True,
    pause_s: float = 0.05,
) -> IngestOutcome:
    """Pull USD-M perpetual klines from ``start_date`` (UTC) through ``end_date`` (default now).

    Each OHLCV bar, mark-price bar, and funding event maps to one
    :class:`~crucibo.models.TradeTick` with deterministic ``ts_event_ns`` ordering
    (sub-ms offsets disambiguate colliding ms timestamps).
    """
    sym = symbol.upper()
    if interval not in VALID_INTERVALS:
        raise ValueError(f"interval must be one of {VALID_INTERVALS}, got {interval!r}")

    start_ms = parse_start_date_ms(start_date)
    if end_date is not None:
        end_ms = parse_end_date_ms(end_date)
    else:
        end_ms = int(datetime.now(UTC).timestamp() * 1000)

    if start_ms > end_ms:
        raise ValueError(f"start_date {start_date!r} is after end_date {end_date!r}")

    if silver_root is None:
        silver_root = Path(os.environ.get("CRUCIBO_DATA_ROOT", "data"))

    end_suffix = end_date or "latest"
    slice_dir = (
        silver_root
        / "silver"
        / "binance"
        / f"symbol={sym}"
        / f"interval={interval}"
        / f"start={start_date}"
        / f"end={end_suffix}"
    )
    parquet_path = slice_dir / "bars.parquet"
    manifest_path = slice_dir / "manifest.json"

    ingest_ns = utc_now_ns()
    with httpx.Client(timeout=120.0) as client:
        ticks = fetch_futures_klines(
            client,
            symbol=sym,
            interval=interval,
            start_ms=start_ms,
            end_ms=end_ms,
            ts_ingest_ns=ingest_ns,
            include_mark_price=include_mark_price,
            include_funding=include_funding,
            pause_s=pause_s,
        )

    kline_count = sum(
        1 for t in ticks if t.conditions and t.conditions.startswith("binance:futures-")
    )
    mark_price_count = sum(
        1 for t in ticks if t.conditions and t.conditions.startswith("binance:mark-price-")
    )
    funding_count = sum(1 for t in ticks if t.conditions == "binance:funding-rate")

    ticks_to_parquet(ticks, parquet_path)

    first_event = None
    last_event = None
    if ticks:
        first_event = (
            datetime.fromtimestamp(ticks[0].ts_event_ns / 1e9, tz=UTC)
            .isoformat()
            .replace("+00:00", "Z")
        )
        last_event = (
            datetime.fromtimestamp(ticks[-1].ts_event_ns / 1e9, tz=UTC)
            .isoformat()
            .replace("+00:00", "Z")
        )

    gh = git_commit or os.environ.get("CRUCIBO_GIT_SHA", "").strip() or None
    manifest = {
        "vendor": "binance",
        "market": "usd-m-futures",
        "endpoint_klines": "/fapi/v1/klines",
        "endpoint_mark_price": "/fapi/v1/markPriceKlines" if include_mark_price else None,
        "endpoint_funding": "/fapi/v1/fundingRate" if include_funding else None,
        "symbol": sym,
        "interval": interval,
        "start_date_utc": start_date,
        "end_date_utc": end_date,
        "fetched_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "first_event_utc": first_event,
        "last_event_utc": last_event,
        "row_count": len(ticks),
        "kline_count": kline_count,
        "mark_price_count": mark_price_count,
        "funding_count": funding_count,
        "parquet_path": str(parquet_path.resolve()),
        "parquet_sha256": _sha256(parquet_path) if ticks else None,
        "tick_ts_ingest_ns_batch": ingest_ns,
        "git_sha": gh,
        "schema_version_tick": 1,
        "note": (
            "Each kline row → TradeTick at bar close (price=close, size=volume). "
            "Mark-price klines use conditions=binance:mark-price-{interval}. "
            "Funding rates use conditions=binance:funding-rate with price=fundingRate. "
            "Sub-ms ns offsets ensure deterministic event-time ordering."
        ),
    }
    _write_manifest(manifest_path=manifest_path, manifest=manifest)
    return IngestOutcome(
        parquet_path=parquet_path,
        manifest_path=manifest_path,
        row_count=len(ticks),
        kline_count=kline_count,
        mark_price_count=mark_price_count,
        funding_count=funding_count,
    )
