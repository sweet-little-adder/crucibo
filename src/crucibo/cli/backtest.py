"""crucibo backtest — event-driven OHLCV simulation."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from crucibo.backtest.economics import EconomicsConfig
from crucibo.backtest.runner import run_backtest, summarize_backtest
from crucibo.config import load_config, resolve_data_root
from crucibo.core.types import Vendor, normalize_av_interval
from crucibo.data.resolve import load_backtest_bars
from crucibo.data.validator import validate_bars
from crucibo.reporting.bundle import write_backtest_bundle
from crucibo.strategies.registry import list_strategies, resolve_strategy

console = Console()
backtest_app = typer.Typer(help="Run event-driven backtests on ingested OHLCV bars.")


@backtest_app.callback(invoke_without_command=True)
def backtest(
    strategy: Annotated[
        str,
        typer.Option("--strategy", "-s", help="ma_crossover | mean_reversion"),
    ],
    symbol: Annotated[str, typer.Option("--symbol", help="Ticker, e.g. AAPL")],
    interval: Annotated[str, typer.Option("--interval", "-i", help="daily | 5min | ...")] = "daily",
    vendor: Annotated[str, typer.Option("--vendor", "-v", help="alphavantage (default)")] = "alphavantage",
    start: Annotated[str | None, typer.Option("--start", help="NY date YYYY-MM-DD inclusive")] = None,
    end: Annotated[str | None, typer.Option("--end", help="NY date YYYY-MM-DD inclusive")] = None,
    bars_path: Annotated[Path | None, typer.Option("--bars-path", help="Override parquet path")] = None,
    fast: Annotated[int, typer.Option("--fast", help="MA fast period")] = 12,
    slow: Annotated[int, typer.Option("--slow", help="MA slow period")] = 26,
    lookback: Annotated[int, typer.Option("--lookback", help="Mean-reversion lookback")] = 20,
    entry_z: Annotated[float, typer.Option("--entry-z", help="Mean-reversion z threshold")] = 1.0,
    target_shares: Annotated[int, typer.Option("--target-shares", help="Shares when long")] = 100,
    initial_cash: Annotated[float | None, typer.Option("--initial-cash")] = None,
    fee_bps: Annotated[float | None, typer.Option("--fee-bps")] = None,
    slippage_bps: Annotated[float | None, typer.Option("--slippage-bps")] = None,
    latency_bars: Annotated[int, typer.Option("--latency-bars", help="0=fill at close, 1=next open")] = 0,
    max_position_shares: Annotated[int | None, typer.Option("--max-position-shares")] = None,
    data_root: Annotated[Path | None, typer.Option("--data-root")] = None,
) -> None:
    """Backtest a registered strategy on local OHLCV data."""
    root = resolve_data_root(data_root)
    vendor_key = vendor.strip().lower()
    if vendor_key != Vendor.ALPHAVANTAGE.value:
        console.print("[red]Phase 2 backtest supports alphavantage (US stocks) first.[/red]")
        raise typer.Exit(code=2)

    norm_interval = normalize_av_interval(interval)
    defaults = load_config().backtest

    try:
        bars, source_path = load_backtest_bars(
            data_root=root,
            vendor=Vendor.ALPHAVANTAGE,
            symbol=symbol,
            interval=norm_interval,
            bars_path=bars_path,
            start=start,
            end=end,
        )
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc

    report = validate_bars(bars, expected_interval=norm_interval)
    if not report.ok:
        console.print("[red]bar validation failed:[/red] " + "; ".join(report.issues))
        raise typer.Exit(code=2)

    strat_key = strategy.strip().lower().replace("-", "_")
    strat_kwargs: dict[str, int | float] = {"target_shares": target_shares}
    if strat_key == "ma_crossover":
        strat_kwargs.update({"fast": fast, "slow": slow})
    elif strat_key == "mean_reversion":
        strat_kwargs.update({"lookback": lookback, "entry_z": entry_z})

    try:
        strat = resolve_strategy(strategy, **strat_kwargs)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print(f"Available: {', '.join(list_strategies())}")
        raise typer.Exit(code=2) from exc

    econ = EconomicsConfig(
        initial_cash=initial_cash if initial_cash is not None else defaults.initial_cash,
        fee_bps=fee_bps if fee_bps is not None else defaults.fee_bps,
        slippage_bps=slippage_bps if slippage_bps is not None else defaults.slippage_bps,
        latency_bars=latency_bars,
        max_position_shares=max_position_shares,
    )

    try:
        outcome = run_backtest(strategy=strat, bars=bars, cfg=econ)
    except ValueError as exc:
        console.print(f"[red]backtest failed:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    metrics = summarize_backtest(econ, outcome, interval=norm_interval)
    manifest = {
        "cmd": "backtest",
        "strategy": strat_key,
        "symbol": symbol.upper(),
        "interval": norm_interval,
        "vendor": vendor_key,
        "start": start,
        "end": end,
        "bars_path": str(source_path),
        "bar_count": len(bars),
        "economics": {
            "initial_cash": econ.initial_cash,
            "fee_bps": econ.fee_bps,
            "slippage_bps": econ.slippage_bps,
            "latency_bars": econ.latency_bars,
            "max_position_shares": econ.max_position_shares,
        },
        "strategy_params": strat_kwargs,
        "metrics": metrics,
        "final_cash": outcome.final_cash,
        "final_shares": outcome.final_shares,
    }
    out_dir, run_id = write_backtest_bundle(
        outcome=outcome,
        manifest=manifest,
        symbol=symbol.upper(),
        strategy=strat_key,
    )

    table = Table(title=f"Backtest {run_id}", show_header=True, header_style="bold")
    table.add_column("metric")
    table.add_column("value")
    table.add_row("strategy", strat_key)
    table.add_row("symbol", symbol.upper())
    table.add_row("bars", str(len(bars)))
    table.add_row("fills", str(metrics["fills_count"]))
    table.add_row("equity start", f"${metrics['equity_start']:,.2f}")
    table.add_row("equity end", f"${metrics['equity_end']:,.2f}")
    table.add_row("pnl", f"${metrics['pnl_cash']:,.2f}")
    table.add_row("return", f"{metrics['return_pct']:.2f}%")
    table.add_row("max drawdown", f"${metrics['max_drawdown']:,.2f}")
    if metrics.get("sharpe") is not None:
        table.add_row("sharpe", f"{metrics['sharpe']:.3f}")
    if metrics.get("sortino") is not None:
        table.add_row("sortino", f"{metrics['sortino']:.3f}")
    table.add_row("run dir", str(out_dir))
    table.add_row("report", f"crucibo report --run-id {run_id}")
    console.print(table)