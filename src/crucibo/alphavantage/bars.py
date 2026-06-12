"""Alpha Vantage OHLCV bars → TradeTick silver slices (free tier friendly)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from crucibo.io_parquet import ticks_to_parquet
from crucibo.models import TradeTick, utc_now_ns
from crucibo.settings import alpha_vantage_api_key

ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"
NY = ZoneInfo("America/New_York")

VALID_INTRADAY_INTERVALS = ("1min", "5min", "15min", "30min", "60min")


def _raise_for_av_payload(payload: dict[str, Any], *, what: str) -> None:
    if "Error Message" in payload:
        raise RuntimeError(f"Alpha Vantage error ({what}): {payload['Error Message']}")
    if "Note" in payload:
        raise RuntimeError(
            f"Alpha Vantage rate limit ({what}): {payload['Note']} "
            "(free tier: 25 requests/day, 5/minute)."
        )
    if "Information" in payload:
        raise RuntimeError(f"Alpha Vantage ({what}): {payload['Information']}")


def parse_av_daily_ts(day: str) -> int:
    """Map AV daily bar date → event ns at 16:00 America/New_York (approx close)."""
    dt = datetime.strptime(day, "%Y-%m-%d").replace(hour=16, minute=0, second=0, tzinfo=NY)
    return int(dt.timestamp() * 1_000_000_000)


def parse_av_intraday_ts(stamp: str) -> int:
    dt = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=NY)
    return int(dt.timestamp() * 1_000_000_000)


def av_bar_to_tick(
    *,
    symbol: str,
    ts_event_ns: int,
    close: float,
    volume: int,
    bar_kind: str,
    ts_ingest_ns: int,
) -> TradeTick:
    return TradeTick(
        ts_event_ns=ts_event_ns,
        ts_ingest_ns=ts_ingest_ns,
        symbol=symbol.upper(),
        price=close,
        size=max(volume, 1),
        conditions=f"alphavantage:{bar_kind}",
    )


def daily_rows_to_ticks(
    rows: dict[str, dict[str, str]],
    *,
    symbol: str,
    ts_ingest_ns: int,
) -> list[TradeTick]:
    ticks: list[TradeTick] = []
    for day in sorted(rows):
        bar = rows[day]
        ticks.append(
            av_bar_to_tick(
                symbol=symbol,
                ts_event_ns=parse_av_daily_ts(day),
                close=float(bar["4. close"]),
                volume=int(float(bar["5. volume"])),
                bar_kind="daily",
                ts_ingest_ns=ts_ingest_ns,
            )
        )
    return ticks


def intraday_rows_to_ticks(
    rows: dict[str, dict[str, str]],
    *,
    symbol: str,
    interval: str,
    ts_ingest_ns: int,
    day: str | None = None,
) -> list[TradeTick]:
    ticks: list[TradeTick] = []
    for stamp in sorted(rows):
        if day is not None and not stamp.startswith(day):
            continue
        bar = rows[stamp]
        ticks.append(
            av_bar_to_tick(
                symbol=symbol,
                ts_event_ns=parse_av_intraday_ts(stamp),
                close=float(bar["4. close"]),
                volume=int(float(bar["5. volume"])),
                bar_kind=f"intraday-{interval}",
                ts_ingest_ns=ts_ingest_ns,
            )
        )
    return ticks


def fetch_alpha_vantage(
    client: httpx.Client,
    *,
    api_key: str,
    params: dict[str, str],
) -> dict[str, Any]:
    merged = {"apikey": api_key, **params}
    response = client.get(ALPHA_VANTAGE_BASE, params=merged, timeout=60.0)
    response.raise_for_status()
    payload = response.json()
    _raise_for_av_payload(payload, what=params.get("function", "query"))
    return payload


def fetch_daily_bars(client: httpx.Client, *, api_key: str, symbol: str) -> list[TradeTick]:
    ingest_ns = utc_now_ns()
    payload = fetch_alpha_vantage(
        client,
        api_key=api_key,
        params={
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol.upper(),
            "outputsize": "compact",
        },
    )
    series = payload.get("Time Series (Daily)")
    if not series:
        raise RuntimeError(f"Alpha Vantage daily response missing series: keys={sorted(payload)!r}")
    return daily_rows_to_ticks(series, symbol=symbol, ts_ingest_ns=ingest_ns)


def fetch_intraday_bars(
    client: httpx.Client,
    *,
    api_key: str,
    symbol: str,
    interval: str,
    day: str | None = None,
) -> list[TradeTick]:
    if interval not in VALID_INTRADAY_INTERVALS:
        raise ValueError(f"interval must be one of {VALID_INTRADAY_INTERVALS}, got {interval!r}")
    ingest_ns = utc_now_ns()
    payload = fetch_alpha_vantage(
        client,
        api_key=api_key,
        params={
            "function": "TIME_SERIES_INTRADAY",
            "symbol": symbol.upper(),
            "interval": interval,
            "outputsize": "compact",
        },
    )
    meta_key = f"Time Series ({interval})"
    series = payload.get(meta_key)
    if not series:
        raise RuntimeError(f"Alpha Vantage intraday response missing {meta_key!r}")
    ticks = intraday_rows_to_ticks(
        series,
        symbol=symbol,
        interval=interval,
        ts_ingest_ns=ingest_ns,
        day=day,
    )
    if day is not None and not ticks:
        raise RuntimeError(
            f"no intraday bars for {symbol.upper()} on {day} "
            "(compact window may not reach that date)"
        )
    return ticks


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


def _write_manifest(
    *,
    manifest_path: Path,
    manifest: dict[str, Any],
) -> None:
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def ingest_alpha_vantage_daily(
    *,
    symbol: str,
    silver_root: Path | None = None,
    git_commit: str | None = None,
) -> IngestOutcome:
    """~100 daily bars in **one** free-tier request."""
    api_key = alpha_vantage_api_key()
    sym = symbol.upper()
    if silver_root is None:
        silver_root = Path(os.environ.get("CRUCIBO_DATA_ROOT", "data"))

    slice_dir = silver_root / "silver" / "alphavantage" / f"symbol={sym}" / "interval=daily"
    parquet_path = slice_dir / "bars.parquet"
    manifest_path = slice_dir / "manifest.json"

    with httpx.Client(timeout=60.0) as client:
        ticks = fetch_daily_bars(client, api_key=api_key, symbol=sym)

    ticks_to_parquet(ticks, parquet_path)
    first_day = None
    last_day = None
    if ticks:
        first_day = datetime.fromtimestamp(ticks[0].ts_event_ns / 1e9, tz=UTC).strftime("%Y-%m-%d")
        last_day = datetime.fromtimestamp(ticks[-1].ts_event_ns / 1e9, tz=UTC).strftime("%Y-%m-%d")

    gh = git_commit or os.environ.get("CRUCIBO_GIT_SHA", "").strip() or None
    manifest = {
        "vendor": "alphavantage",
        "endpoint": "TIME_SERIES_DAILY",
        "symbol": sym,
        "interval": "daily",
        "outputsize": "compact",
        "first_day_utc": first_day,
        "last_day_utc": last_day,
        "fetched_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "row_count": len(ticks),
        "parquet_path": str(parquet_path.resolve()),
        "parquet_sha256": _sha256(parquet_path) if ticks else None,
        "git_sha": gh,
        "schema_version_tick": 1,
        "note": "Each row is a daily bar mapped to TradeTick (close price). Not tick data.",
    }
    _write_manifest(manifest_path=manifest_path, manifest=manifest)
    return IngestOutcome(
        parquet_path=parquet_path,
        manifest_path=manifest_path,
        row_count=len(ticks),
    )


def ingest_alpha_vantage_intraday(
    *,
    symbol: str,
    interval: str = "5min",
    day: str | None = None,
    silver_root: Path | None = None,
    git_commit: str | None = None,
    pause_s: float = 0.0,
) -> IngestOutcome:
    """Intraday bars (~100 points compact). Optional ``day`` filters one UTC calendar date."""
    api_key = alpha_vantage_api_key()
    sym = symbol.upper()
    if silver_root is None:
        silver_root = Path(os.environ.get("CRUCIBO_DATA_ROOT", "data"))

    day_suffix = f"date={day}" if day else "latest"
    slice_dir = (
        silver_root
        / "silver"
        / "alphavantage"
        / f"symbol={sym}"
        / f"interval={interval}"
        / day_suffix
    )
    parquet_path = slice_dir / "bars.parquet"
    manifest_path = slice_dir / "manifest.json"

    if pause_s > 0:
        time.sleep(pause_s)

    with httpx.Client(timeout=60.0) as client:
        ticks = fetch_intraday_bars(
            client,
            api_key=api_key,
            symbol=sym,
            interval=interval,
            day=day,
        )

    ticks_to_parquet(ticks, parquet_path)
    gh = git_commit or os.environ.get("CRUCIBO_GIT_SHA", "").strip() or None
    manifest = {
        "vendor": "alphavantage",
        "endpoint": "TIME_SERIES_INTRADAY",
        "symbol": sym,
        "interval": interval,
        "filter_day": day,
        "outputsize": "compact",
        "fetched_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "row_count": len(ticks),
        "parquet_path": str(parquet_path.resolve()),
        "parquet_sha256": _sha256(parquet_path) if ticks else None,
        "git_sha": gh,
        "schema_version_tick": 1,
        "note": (
            "Each row is an intraday bar mapped to TradeTick (close price). "
            "Free tier: 15-min delayed."
        ),
    }
    _write_manifest(manifest_path=manifest_path, manifest=manifest)
    return IngestOutcome(
        parquet_path=parquet_path,
        manifest_path=manifest_path,
        row_count=len(ticks),
    )
