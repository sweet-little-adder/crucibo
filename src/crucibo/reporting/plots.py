"""Equity curve and drawdown charts for backtest runs."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl

NY = ZoneInfo("America/New_York")


def _ts_to_ny_dates(ts_ns: list[int]) -> list[datetime]:
    return [datetime.fromtimestamp(t / 1_000_000_000, tz=NY) for t in ts_ns]


def plot_backtest_report(
    *,
    equity_curve: list[dict[str, float | int]],
    out_path: Path,
    title: str,
) -> Path:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ImportError(
            "matplotlib is required for plots. Install with: pip install 'crucibo[plots]'"
        ) from exc

    if not equity_curve:
        raise ValueError("empty equity curve")

    df = pl.DataFrame(equity_curve).sort("ts_event_ns")
    dates = _ts_to_ny_dates(df["ts_event_ns"].to_list())
    equity = df["equity_marked"].to_list()
    drawdown = df["drawdown"].to_list()

    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, (ax_eq, ax_dd) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    fig.suptitle(title, fontsize=12)

    ax_eq.plot(dates, equity, color="#2563eb", linewidth=1.5)
    ax_eq.set_ylabel("Equity ($)")
    ax_eq.grid(True, alpha=0.3)
    ax_eq.ticklabel_format(style="plain", axis="y")

    ax_dd.fill_between(dates, drawdown, color="#dc2626", alpha=0.35)
    ax_dd.plot(dates, drawdown, color="#dc2626", linewidth=1.0)
    ax_dd.set_ylabel("Drawdown ($)")
    ax_dd.set_xlabel("Date (America/New_York)")
    ax_dd.grid(True, alpha=0.3)
    ax_dd.invert_yaxis()

    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return out_path