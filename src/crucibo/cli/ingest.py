"""crucibo ingest — US equities first (Alpha Vantage), crypto second."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from crucibo.config import resolve_data_root
from crucibo.core.types import Vendor
from crucibo.data.vendors.alphavantage import ingest_alphavantage

console = Console()
ingest_app = typer.Typer(help="Ingest historical market data into local Parquet storage.")


@ingest_app.callback(invoke_without_command=True)
def ingest(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="Ticker, e.g. AAPL")],
    interval: Annotated[
        str,
        typer.Option(
            "--interval",
            "-i",
            help="US stocks: daily | 1min | 5min | 15min | 30min | 60min",
        ),
    ] = "daily",
    vendor: Annotated[
        str,
        typer.Option(
            "--vendor",
            "-v",
            help="alphavantage (US stocks, default) | binance (crypto, phase 2)",
        ),
    ] = "alphavantage",
    day: Annotated[
        str | None,
        typer.Option("--day", help="Filter intraday to one calendar day YYYY-MM-DD"),
    ] = None,
    data_root: Annotated[
        Path | None,
        typer.Option("--data-root", help="Override CRUCIBO_DATA_ROOT"),
    ] = None,
) -> None:
    """Download OHLCV bars and register them in the local catalog."""
    root = resolve_data_root(data_root)
    vendor_key = vendor.strip().lower()

    if vendor_key == Vendor.ALPHAVANTAGE.value:
        try:
            result = ingest_alphavantage(
                symbol=symbol,
                interval=interval,
                data_root=root,
                day=day,
            )
        except (RuntimeError, ValueError) as exc:
            console.print(f"[red]ingest failed:[/red] {exc}")
            raise typer.Exit(code=2) from exc

        table = Table(title="Ingest complete", show_header=True, header_style="bold")
        table.add_column("field")
        table.add_column("value")
        table.add_row("vendor", result.vendor.value)
        table.add_row("symbol", result.symbol)
        table.add_row("interval", result.interval)
        table.add_row("bars", str(result.row_count))
        table.add_row("first day", result.first_day or "—")
        table.add_row("last day", result.last_day or "—")
        table.add_row("parquet", str(result.parquet_path))
        table.add_row("manifest", str(result.manifest_path))
        console.print(table)
        return

    if vendor_key == Vendor.BINANCE.value:
        console.print(
            "[yellow]Binance via `crucibo ingest --vendor binance` ships in Phase 1b.[/yellow]\n"
            "Legacy: [bold]crucibo ingest-binance --symbol BTCUSDT ...[/bold]"
        )
        raise typer.Exit(code=2)

    console.print(f"[red]unknown vendor {vendor!r}[/red] (try alphavantage | binance)")
    raise typer.Exit(code=2)