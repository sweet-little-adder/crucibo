"""Report Typer CLI."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from crucibo.cli.app import app

runner = CliRunner()


def _write_run(tmp_path: Path) -> str:
    run_id = "bt_TST_ma_crossover_test"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    n = 30
    eq = pl.DataFrame(
        {
            "ts_event_ns": list(range(n)),
            "equity_marked": [1_000_000.0 + i * 100.0 for i in range(n)],
            "cash": [1_000_000.0] * n,
            "shares": [0] * n,
            "mid_price": [100.0] * n,
            "drawdown": [0.0] * n,
        }
    )
    eq.write_parquet(run_dir / "equity_curve.parquet")
    pl.DataFrame(
        schema={
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
    ).write_parquet(run_dir / "fills.parquet")
    manifest = {
        "run_id": run_id,
        "symbol": "TST",
        "strategy": "ma_crossover",
        "interval": "daily",
        "bar_count": n,
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run_id


def test_report_cli_latest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CRUCIBO_DATA_ROOT", str(tmp_path))
    _write_run(tmp_path)

    result = runner.invoke(
        app,
        ["report", "--run-id", "latest", "--no-plot"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "sharpe" in result.stdout.lower()
    assert (tmp_path / "runs").exists()