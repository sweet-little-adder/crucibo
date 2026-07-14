"""Backtest run bundle loading."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from crucibo.reporting.runs import list_backtest_runs, load_backtest_run, resolve_run_dir


def _write_minimal_run(tmp_path: Path, run_id: str) -> Path:
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    eq = pl.DataFrame(
        {
            "ts_event_ns": [1, 2, 3],
            "equity_marked": [1_000_000.0, 1_001_000.0, 1_002_000.0],
            "cash": [1_000_000.0, 900_000.0, 900_000.0],
            "shares": [0, 10, 10],
            "mid_price": [100.0, 100.1, 100.2],
            "drawdown": [0.0, 0.0, 0.0],
        }
    )
    eq.write_parquet(run_dir / "equity_curve.parquet")
    pl.DataFrame(
        {
            "ts_event_ns": [2],
            "symbol": ["TST"],
            "side": ["BUY"],
            "qty_shares": [10],
            "exec_price": [100.0],
            "fee_cash": [0.4],
            "notional": [1000.0],
            "cash_after": [999_000.0],
            "shares_after": [10],
            "signal_bar_index": [1],
        }
    ).write_parquet(run_dir / "fills.parquet")
    manifest = {
        "run_id": run_id,
        "cmd": "backtest",
        "symbol": "TST",
        "strategy": "ma_crossover",
        "interval": "daily",
        "bar_count": 3,
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run_dir


def test_resolve_latest(tmp_path: Path) -> None:
    import os
    import time

    older = _write_minimal_run(tmp_path, "bt_TST_ma_crossover_1")
    time.sleep(0.01)
    newer = _write_minimal_run(tmp_path, "bt_TST_ma_crossover_2")
    os.utime(newer, (newer.stat().st_mtime + 10, newer.stat().st_mtime + 10))
    os.utime(older, (older.stat().st_mtime, older.stat().st_mtime))
    resolved = resolve_run_dir(run_id="latest", data_root=tmp_path)
    assert resolved.name == newer.name


def test_load_backtest_run(tmp_path: Path) -> None:
    run_dir = _write_minimal_run(tmp_path, "bt_TST_ma_crossover_99")
    run = load_backtest_run(run_dir=run_dir)
    assert run.run_id == "bt_TST_ma_crossover_99"
    assert len(run.equity_curve) == 3
    assert len(run.fills) == 1


def test_list_backtest_runs(tmp_path: Path) -> None:
    _write_minimal_run(tmp_path, "bt_A_1")
    _write_minimal_run(tmp_path, "pq_legacy_1")
    runs = list_backtest_runs(data_root=tmp_path)
    assert len(runs) == 1
    assert runs[0].name.startswith("bt_")