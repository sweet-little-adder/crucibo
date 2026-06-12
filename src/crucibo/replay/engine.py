"""Naive instantaneous fill vs last tick mid (sandbox only)."""

from __future__ import annotations

from dataclasses import dataclass

from crucibo.models import TradeTick
from crucibo.replay.strategies import TickStrategy


@dataclass
class ReplayConfig:
    """Economic knobs—rough stand-ins until Phase 3 schedule objects exist."""

    initial_cash: float = 1_000_000.0
    slip_bps: float = 2.0
    fee_per_share: float = 0.005


@dataclass
class ReplayOutcome:
    fills: list[dict[str, float | int | str]]
    equity_curve: list[dict[str, float | int]]
    final_cash: float
    final_shares: int


def replay_ticks(
    strategy: TickStrategy,
    ticks: list[TradeTick],
    cfg: ReplayConfig,
) -> ReplayOutcome:
    """Single-threaded deterministic replay sorted by ``ts_event_ns``.

    - Fills instantly at ``tick.price`` adjusted by symmetric ``slip_bps`` on the trade direction.
    - Long-only bookkeeping; rejects negative cash purchases.
    """
    if not ticks:
        return ReplayOutcome(
            fills=[],
            equity_curve=[],
            final_cash=cfg.initial_cash,
            final_shares=0,
        )

    seq = sorted(ticks, key=lambda t: (t.ts_event_ns, t.symbol))
    n = len(seq)
    cash = cfg.initial_cash
    shares = 0
    fills: list[dict[str, float | int | str]] = []
    equity: list[dict[str, float | int]] = []
    slip_m = cfg.slip_bps / 10_000.0

    for i, tick in enumerate(seq):
        want = strategy.desired_shares(
            tick=tick, index=i, n_ticks=n, position=shares, cash=cash
        )
        if want < 0:
            raise ValueError("negative target shares not supported in toy engine")
        delta = want - shares
        if delta != 0:
            if delta > 0:
                exec_px = tick.price * (1.0 + slip_m)
                gross = delta * exec_px
                fee = delta * cfg.fee_per_share
                total = gross + fee
                if total > cash + 1e-9:
                    raise ValueError(
                        f"insufficient cash for buy at tick {i}: need {total:.2f} have {cash:.2f}"
                    )
                cash -= total
                shares += delta
                side = "BUY"
            else:
                qty = -delta
                exec_px = tick.price * (1.0 - slip_m)
                gross = qty * exec_px
                fee = qty * cfg.fee_per_share
                cash += gross - fee
                shares -= qty
                side = "SELL"
            fills.append(
                {
                    "ts_event_ns": tick.ts_event_ns,
                    "symbol": tick.symbol,
                    "side": side,
                    "qty_shares": abs(delta),
                    "exec_price": exec_px,
                    "fee_cash": fee,
                    "cash_after": cash,
                    "shares_after": shares,
                    "mid_price_tick": tick.price,
                    "slip_bps": cfg.slip_bps,
                }
            )
        assert shares >= 0
        mark = cash + shares * tick.price
        equity.append(
            {
                "ts_event_ns": tick.ts_event_ns,
                "equity_marked": mark,
                "cash": cash,
                "shares": shares,
                "mid_price": tick.price,
            }
        )

    return ReplayOutcome(
        fills=fills,
        equity_curve=equity,
        final_cash=cash,
        final_shares=shares,
    )


def summarize_pnl(initial: ReplayConfig, out: ReplayOutcome) -> dict[str, float]:
    if not out.equity_curve:
        return {
            "equity_start": float(initial.initial_cash),
            "equity_end": float(initial.initial_cash),
            "pnl_cash_approx": 0.0,
        }
    eq0 = out.equity_curve[0]["equity_marked"]
    eq1 = out.equity_curve[-1]["equity_marked"]
    return {
        "equity_start": float(eq0),
        "equity_end": float(eq1),
        "pnl_cash_approx": float(eq1) - float(eq0),
    }
