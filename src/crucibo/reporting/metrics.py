"""Portfolio metrics from equity curves and fill logs."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

_PERIODS_PER_YEAR: dict[str, int] = {
    "daily": 252,
    "1min": 252 * 390,
    "5min": 252 * 78,
    "15min": 252 * 26,
    "30min": 252 * 13,
    "60min": 252 * 6,
}


def periods_per_year(interval: str) -> int:
    key = interval.strip().lower()
    return _PERIODS_PER_YEAR.get(key, 252)


def equity_returns(equity: list[float]) -> list[float]:
    if len(equity) < 2:
        return []
    out: list[float] = []
    for i in range(1, len(equity)):
        prev = equity[i - 1]
        if prev <= 0:
            out.append(0.0)
        else:
            out.append((equity[i] / prev) - 1.0)
    return out


def sharpe_ratio(returns: list[float], *, periods_per_year: int) -> float | None:
    if len(returns) < 2:
        return None
    arr = np.asarray(returns, dtype=np.float64)
    std = float(arr.std(ddof=1))
    if std < 1e-15:
        return None
    return float(arr.mean() / std * math.sqrt(periods_per_year))


def sortino_ratio(returns: list[float], *, periods_per_year: int) -> float | None:
    if len(returns) < 2:
        return None
    arr = np.asarray(returns, dtype=np.float64)
    downside = arr[arr < 0]
    if downside.size < 1:
        return None
    dd_std = float(downside.std(ddof=1))
    if dd_std < 1e-15:
        return None
    return float(arr.mean() / dd_std * math.sqrt(periods_per_year))


def calmar_ratio(*, return_pct: float, max_drawdown_pct: float, bar_count: int, periods_per_year: int) -> float | None:
    if max_drawdown_pct <= 1e-12 or bar_count < 1:
        return None
    years = bar_count / periods_per_year
    if years <= 0:
        return None
    annualized = ((1.0 + return_pct / 100.0) ** (1.0 / years) - 1.0) * 100.0
    return annualized / max_drawdown_pct


def round_trip_pnls(fills: list[dict[str, Any]]) -> list[float]:
    """Long-only round trips: BUY opens, SELL closes."""
    pnls: list[float] = []
    entry_cost = 0.0
    for fill in fills:
        side = str(fill["side"])
        notional = float(fill["notional"])
        fee = float(fill["fee_cash"])
        if side == "BUY":
            entry_cost += notional + fee
        elif side == "SELL":
            proceeds = notional - fee
            pnls.append(proceeds - entry_cost)
            entry_cost = 0.0
    return pnls


def trade_stats(pnls: list[float]) -> dict[str, float | int | None]:
    if not pnls:
        return {
            "trades_count": 0,
            "win_rate_pct": None,
            "profit_factor": None,
            "expectancy": None,
            "avg_win": None,
            "avg_loss": None,
        }

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    win_rate = (len(wins) / len(pnls)) * 100.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 1e-12 else None
    avg_win = (gross_profit / len(wins)) if wins else 0.0
    avg_loss = (gross_loss / len(losses)) if losses else 0.0
    loss_rate = len(losses) / len(pnls)
    expectancy = (win_rate / 100.0) * avg_win - loss_rate * avg_loss

    return {
        "trades_count": len(pnls),
        "win_rate_pct": win_rate,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "avg_win": avg_win if wins else None,
        "avg_loss": avg_loss if losses else None,
    }


def compute_metrics(
    *,
    equity_curve: list[dict[str, float | int]],
    fills: list[dict[str, Any]],
    interval: str = "daily",
) -> dict[str, float | int | None]:
    if not equity_curve:
        return {
            "equity_start": 0.0,
            "equity_end": 0.0,
            "pnl_cash": 0.0,
            "return_pct": 0.0,
            "max_drawdown": 0.0,
            "max_drawdown_pct": 0.0,
            "fills_count": 0,
            "sharpe": None,
            "sortino": None,
            "calmar": None,
            "trades_count": 0,
            "win_rate_pct": None,
            "profit_factor": None,
            "expectancy": None,
            "avg_win": None,
            "avg_loss": None,
        }

    equity = [float(p["equity_marked"]) for p in equity_curve]
    eq0, eq1 = equity[0], equity[-1]
    pnl = eq1 - eq0
    ret_pct = (pnl / eq0) * 100.0 if eq0 else 0.0

    peak = equity[0]
    max_dd = 0.0
    for e in equity:
        peak = max(peak, e)
        max_dd = max(max_dd, peak - e)
    max_dd_pct = (max_dd / peak) * 100.0 if peak > 0 else 0.0

    ppy = periods_per_year(interval)
    rets = equity_returns(equity)
    trade = trade_stats(round_trip_pnls(fills))

    return {
        "equity_start": eq0,
        "equity_end": eq1,
        "pnl_cash": pnl,
        "return_pct": ret_pct,
        "max_drawdown": max_dd,
        "max_drawdown_pct": max_dd_pct,
        "fills_count": len(fills),
        "sharpe": sharpe_ratio(rets, periods_per_year=ppy),
        "sortino": sortino_ratio(rets, periods_per_year=ppy),
        "calmar": calmar_ratio(
            return_pct=ret_pct,
            max_drawdown_pct=max_dd_pct,
            bar_count=len(equity_curve),
            periods_per_year=ppy,
        ),
        **trade,
    }