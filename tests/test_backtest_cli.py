"""Backtest Typer CLI smoke test."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from crucibo.cli.app import app
from crucibo.core.bar import Bar
from crucibo.core.types import Vendor
from crucibo.data.parquet_store import write_bars

runner = CliRunner()


def _synthetic_aapl_bars(n: int = 60) -> list[Bar]:
    ts_base = 1_735_689_600_000_000_000  # 2025-01-01-ish UTC
    bars: list[Bar] = []
    for i in range(n):
        close = 180.0 + i * 0.5
        bars.append(
            Bar(
                ts_close_ns=ts_base + i * 86_400_000_000_000,
                symbol="AAPL",
                interval="daily",
                vendor=Vendor.ALPHAVANTAGE,
                open=close - 0.2,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=5_000_000.0,
            )
        )
    return bars


def test_backtest_cli_with_bars_path(tmp_path: Path) -> None:
    bars = _synthetic_aapl_bars()
    bars_path = tmp_path / "bars.parquet"
    write_bars(bars, bars_path)

    result = runner.invoke(
        app,
        [
            "backtest",
            "--strategy",
            "ma_crossover",
            "--symbol",
            "AAPL",
            "--interval",
            "daily",
            "--fast",
            "5",
            "--slow",
            "10",
            "--bars-path",
            str(bars_path),
            "--fee-bps",
            "0",
            "--slippage-bps",
            "0",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Backtest bt_" in result.stdout
    assert "fills" in result.stdout.lower()