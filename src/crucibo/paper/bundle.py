"""Persist paper (and live-dry-run) sessions under data/runs/."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from crucibo.paper.engine import PaperConfig, PaperState, latency_summary
from crucibo.replay.bundle import default_runs_parent

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
    "drawdown": pl.Float64,
}


def _git_sha() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def paper_runs_dir(runs_parent: Path | None = None) -> Path:
    """Parent for paper/live bundles: ``<data-root>/runs``."""
    base = runs_parent or default_runs_parent()
    return (base / "runs").resolve()


def write_paper_run_bundle(
    *,
    run_id: str,
    symbol: str,
    interval: str,
    feed: str,
    strategy_name: str,
    model_path: str | None,
    cfg: PaperConfig,
    state: PaperState,
    tick_count: int,
    mode: str = "paper",
    poll_seconds: float | None = None,
    interrupted: bool = False,
    runs_parent: Path | None = None,
    extra_manifest: dict | None = None,
) -> Path:
    """Write equity curve, fills, latency, and run_manifest under data/runs/<run_id>/."""

    out_dir = paper_runs_dir(runs_parent) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    fills_rows = []
    for f in state.fills:
        fills_rows.append(
            {
                "ts_event_ns": int(f["ts_event_ns"]),
                "symbol": str(f["symbol"]),
                "side": str(f["side"]),
                "qty_shares": int(f["qty_shares"]),
                "exec_price": float(f["exec_price"]),
                "fee_cash": float(f["fee_cash"]),
                "cash_after": float(f["cash_after"]),
                "shares_after": int(f["shares_after"]),
                "mid_price_tick": float(f.get("mid_price_tick", f["exec_price"])),
                "slip_bps": float(f.get("slip_bps", cfg.slip_bps)),
            }
        )
    fills_df = pl.DataFrame(fills_rows) if fills_rows else pl.DataFrame(schema=_FILL_SCHEMA)
    fills_df.write_parquet(out_dir / "sim_fills.parquet")

    eq_rows = [
        {
            "ts_event_ns": int(p["ts_event_ns"]),
            "equity_marked": float(p["equity_marked"]),
            "cash": float(p["cash"]),
            "shares": int(p["shares"]),
            "mid_price": float(p["mid_price"]),
            "drawdown": float(p.get("drawdown", 0.0)),
        }
        for p in state.equity_curve
    ]
    eq_df = pl.DataFrame(eq_rows) if eq_rows else pl.DataFrame(schema=_EQ_SCHEMA)
    eq_df.write_parquet(out_dir / "equity_curve.parquet")

    mark = state.last_mark_price or 0.0
    final_equity = state.equity_at(mark) if mark else state.cash
    lat = latency_summary(state)

    manifest: dict = {
        "manifest_schema": 2,
        "mode": mode,
        "feed": feed,
        "symbol": symbol,
        "interval": interval,
        "strategy": strategy_name,
        "model_path": model_path,
        "tick_count": tick_count,
        "killed": state.killed,
        "kill_reason": state.kill_reason,
        "interrupted": interrupted,
        "final_cash": state.cash,
        "final_shares": state.shares,
        "final_equity": final_equity,
        "fills_count": len(state.fills),
        "equity_points": len(state.equity_curve),
        "paper_config": asdict(cfg),
        "latency": lat,
        "git_sha": _git_sha(),
        "written_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "paths": {
            "dir": str(out_dir),
            "fills": str(out_dir / "sim_fills.parquet"),
            "equity_curve": str(out_dir / "equity_curve.parquet"),
        },
    }
    if poll_seconds is not None:
        manifest["poll_seconds"] = poll_seconds
    if extra_manifest:
        manifest.update(extra_manifest)

    text = json.dumps(manifest, indent=2) + "\n"
    (out_dir / "run_manifest.json").write_text(text, encoding="utf-8")
    # Back-compat alias for older tooling
    (out_dir / "paper_manifest.json").write_text(text, encoding="utf-8")
    return out_dir
