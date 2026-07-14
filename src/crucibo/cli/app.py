"""Modern Typer CLI entry (v2)."""

from __future__ import annotations

import typer

from crucibo.cli.backtest import backtest_app
from crucibo.cli.ingest import ingest_app
from crucibo.cli.report import report_app

app = typer.Typer(
    name="crucibo",
    help="Quant backtesting toolkit — US equities first, crypto second.",
    no_args_is_help=True,
)
app.add_typer(ingest_app, name="ingest")
app.add_typer(backtest_app, name="backtest")
app.add_typer(report_app, name="report")