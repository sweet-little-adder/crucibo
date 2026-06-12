"""Persist replay outputs beside ingest slices."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from crucibo.models import utc_now_ns
from crucibo.replay.engine import ReplayOutcome

_FILL_SCHEMA = {
    "ts_event_ns": pl.Int64,
    "symbol": pl.Utf8,
    "side": pl.Utf8,
    "qty_shares": pl.Int64,
    "exec_price": pl.Float64,
    "fee_cash": pl.Float64,
    "cash_after": pl.Float64,
    "shares_after": pl.Int64,
    "mid_price_tick": pl.Float64,
    "slip_bps": pl.Float64,
}

_EQ_SCHEMA = {
    "ts_event_ns": pl.Int64,
    "equity_marked": pl.Float64,
    "cash": pl.Float64,
    "shares": pl.Int64,
    "mid_price": pl.Float64,
}


def default_runs_parent() -> Path:
    root = Path(os.environ.get("CRUCIBO_DATA_ROOT", "data")).resolve()
    return root


def write_run_bundle(
    *,
    outcome: ReplayOutcome,
    manifest: dict,
    run_id: str,
    runs_parent: Path | None = None,
) -> Path:
    base = runs_parent or default_runs_parent()
    out_dir = (base / "runs" / run_id).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    fills_df = (
        pl.DataFrame(outcome.fills) if outcome.fills else pl.DataFrame(schema=_FILL_SCHEMA)
    )
    eq_df = (
        pl.DataFrame(outcome.equity_curve)
        if outcome.equity_curve
        else pl.DataFrame(schema=_EQ_SCHEMA)
    )
    fills_df.write_parquet(out_dir / "sim_fills.parquet")
    eq_df.write_parquet(out_dir / "equity_curve.parquet")

    full_manifest = dict(manifest)
    full_manifest.setdefault("written_at_utc", datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    full_manifest.setdefault("manifest_schema", 1)
    full_manifest.setdefault("paths", {"dir": str(out_dir)})
    manifest_txt = json.dumps(full_manifest, indent=2)
    (out_dir / "run_manifest.json").write_text(manifest_txt, encoding="utf-8")
    return out_dir


def make_run_id(*, prefix: str, symbol: str, strategy: str) -> str:
    """Human-readable-ish id unique enough for local sandboxes."""

    slug = utc_now_ns()
    sym = symbol.upper().replace("/", "-")
    return f"{prefix}_{sym}_{strategy}_{slug}"
