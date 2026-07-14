"""crucibo report — metrics and charts for backtest runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from crucibo.config import resolve_data_root
from crucibo.reporting.metrics import compute_metrics
from crucibo.reporting.plots import plot_backtest_report
from crucibo.reporting.runs import load_backtest_run, resolve_run_dir

console = Console()
report_app = typer.Typer(help="Summarize backtest runs with portfolio metrics and charts.")


def _fmt_metric(key: str, value: float | int | None) -> str:
    if value is None:
        return "—"
    if key.endswith("_pct"):
        return f"{value:.2f}%"
    if key in {"sharpe", "sortino", "calmar", "profit_factor"}:
        return f"{value:.3f}"
    if key in {"equity_start", "equity_end", "pnl_cash", "max_drawdown", "expectancy", "avg_win", "avg_loss"}:
        return f"${value:,.2f}"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


@report_app.callback(invoke_without_command=True)
def report(
    run_id: Annotated[
        str,
        typer.Option("--run-id", "-r", help="Run id or 'latest'"),
    ] = "latest",
    data_root: Annotated[Path | None, typer.Option("--data-root")] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Directory for report artifacts"),
    ] = None,
    plot: Annotated[bool, typer.Option("--plot/--no-plot", help="Write equity_curve.png")] = True,
) -> None:
    """Print portfolio metrics and optionally write chart + metrics JSON."""
    root = resolve_data_root(data_root)

    try:
        run_dir = resolve_run_dir(run_id=run_id, data_root=root)
        run = load_backtest_run(run_dir=run_dir)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc

    interval = str(run.manifest.get("interval", "daily"))
    metrics = compute_metrics(
        equity_curve=run.equity_curve,
        fills=run.fills,
        interval=interval,
    )

    out_dir = (output_dir or run.dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = out_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

    plot_path: Path | None = None
    if plot:
        try:
            sym = str(run.manifest.get("symbol", "SYM"))
            strat = str(run.manifest.get("strategy", "strategy"))
            plot_path = plot_backtest_report(
                equity_curve=run.equity_curve,
                out_path=out_dir / "equity_curve.png",
                title=f"{sym} · {strat} · {run.run_id}",
            )
        except ImportError as exc:
            console.print(f"[yellow]{exc}[/yellow]")
        except ValueError as exc:
            console.print(f"[yellow]plot skipped:[/yellow] {exc}")

    table = Table(title=f"Report {run.run_id}", show_header=True, header_style="bold")
    table.add_column("metric")
    table.add_column("value")

    rows: list[tuple[str, str]] = [
        ("symbol", str(run.manifest.get("symbol", "—"))),
        ("strategy", str(run.manifest.get("strategy", "—"))),
        ("interval", interval),
        ("bars", str(run.manifest.get("bar_count", len(run.equity_curve)))),
        ("equity start", _fmt_metric("equity_start", metrics["equity_start"])),
        ("equity end", _fmt_metric("equity_end", metrics["equity_end"])),
        ("pnl", _fmt_metric("pnl_cash", metrics["pnl_cash"])),
        ("return", _fmt_metric("return_pct", metrics["return_pct"])),
        ("max drawdown", _fmt_metric("max_drawdown", metrics["max_drawdown"])),
        ("max drawdown %", _fmt_metric("max_drawdown_pct", metrics["max_drawdown_pct"])),
        ("sharpe", _fmt_metric("sharpe", metrics["sharpe"])),
        ("sortino", _fmt_metric("sortino", metrics["sortino"])),
        ("calmar", _fmt_metric("calmar", metrics["calmar"])),
        ("fills", str(metrics["fills_count"])),
        ("round trips", str(metrics["trades_count"])),
        ("win rate", _fmt_metric("win_rate_pct", metrics["win_rate_pct"])),
        ("profit factor", _fmt_metric("profit_factor", metrics["profit_factor"])),
        ("expectancy", _fmt_metric("expectancy", metrics["expectancy"])),
        ("metrics file", str(metrics_path)),
    ]
    if plot_path is not None:
        rows.append(("chart", str(plot_path)))

    for label, val in rows:
        table.add_row(label, val)

    console.print(table)