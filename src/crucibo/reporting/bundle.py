"""Persist backtest run artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from crucibo.backtest.runner import BacktestOutcome
from crucibo.replay.bundle import default_runs_parent, make_run_id

_FILL_SCHEMA = {
    "ts_event_ns": pl.Int64,
    "symbol": pl.Utf8,
    "side": pl.Utf8,
    "qty_shares": pl.Int64,
    "exec_price": pl.Float64,
    "fee_cash": pl.Float64,
    "notional": pl.Float64,
    "cash_after": pl.Float64,
    "shares_after": pl.Int64,
    "signal_bar_index": pl.Int64,
}

_EQ_SCHEMA = {
    "ts_event_ns": pl.Int64,
    "equity_marked": pl.Float64,
    "cash": pl.Float64,
    "shares": pl.Int64,
    "mid_price": pl.Float64,
    "drawdown": pl.Float64,
}


def write_backtest_bundle(
    *,
    outcome: BacktestOutcome,
    manifest: dict,
    run_id: str | None = None,
    runs_parent: Path | None = None,
    prefix: str = "bt",
    symbol: str = "SYM",
    strategy: str = "strategy",
) -> tuple[Path, str]:
    parent = runs_parent or default_runs_parent()
    rid = run_id or make_run_id(prefix=prefix, symbol=symbol, strategy=strategy)
    out_dir = (parent / "runs" / rid).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    fills_df = (
        pl.DataFrame(outcome.fills) if outcome.fills else pl.DataFrame(schema=_FILL_SCHEMA)
    )
    eq_df = (
        pl.DataFrame(outcome.equity_curve)
        if outcome.equity_curve
        else pl.DataFrame(schema=_EQ_SCHEMA)
    )
    fills_df.write_parquet(out_dir / "fills.parquet")
    eq_df.write_parquet(out_dir / "equity_curve.parquet")

    full_manifest = dict(manifest)
    full_manifest["run_id"] = rid
    full_manifest.setdefault("written_at_utc", datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    full_manifest.setdefault("manifest_schema", 2)
    full_manifest.setdefault("paths", {"dir": str(out_dir)})
    (out_dir / "run_manifest.json").write_text(
        json.dumps(full_manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    metrics_path = out_dir / "metrics.json"
    if "metrics" in full_manifest:
        metrics_path.write_text(
            json.dumps(full_manifest["metrics"], indent=2) + "\n",
            encoding="utf-8",
        )
    return out_dir, rid