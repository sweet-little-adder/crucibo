"""Lightweight OOS replay — mirrors crucibo economics for morning-star eval."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from morning_star.features.builder import FeatureState
from morning_star.models.baseline import BaselineMLP
from morning_star.ticks import Tick


@dataclass
class EvalConfig:
    initial_cash: float = 1_000_000.0
    slip_bps: float = 2.0
    fee_per_share: float = 0.005


@dataclass
class EvalOutcome:
    fills: list[dict[str, float | int | str]]
    equity_curve: list[dict[str, float | int]]
    final_cash: float
    final_shares: int


def replay_model(
    model: BaselineMLP,
    ticks: list[Tick],
    cfg: EvalConfig,
) -> EvalOutcome:
    if not ticks:
        return EvalOutcome([], [], cfg.initial_cash, 0)

    seq = sorted(ticks, key=lambda t: (t.ts_event_ns, t.symbol))
    state = FeatureState(
        lookback=model.lookback,
        initial_cash=model.initial_cash,
        max_position=model.target_shares,
    )
    cash = cfg.initial_cash
    shares = 0
    fills: list[dict[str, float | int | str]] = []
    equity: list[dict[str, float | int]] = []
    slip_m = cfg.slip_bps / 10_000.0

    for i, tick in enumerate(seq):
        vec = state.update(tick, position=shares, cash=cash)
        want = 0 if vec is None else model.decide_shares(vec)
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
                }
            )
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

    return EvalOutcome(
        fills=fills,
        equity_curve=equity,
        final_cash=cash,
        final_shares=shares,
    )


def summarize_pnl(cfg: EvalConfig, out: EvalOutcome) -> dict[str, float]:
    if not out.equity_curve:
        return {
            "equity_start": float(cfg.initial_cash),
            "equity_end": float(cfg.initial_cash),
            "pnl_cash_approx": 0.0,
        }
    eq0 = out.equity_curve[0]["equity_marked"]
    eq1 = out.equity_curve[-1]["equity_marked"]
    return {
        "equity_start": float(eq0),
        "equity_end": float(eq1),
        "pnl_cash_approx": float(eq1) - float(eq0),
    }


def in_sample_score(
    model: BaselineMLP,
    features: np.ndarray,
    labels: np.ndarray,
) -> dict[str, float]:
    probs = np.array([model.predict_proba(row) for row in features], dtype=np.float64)
    preds = (probs >= model.threshold).astype(np.float64)
    acc = float((preds == labels.reshape(-1)).mean())
    return {"in_sample_accuracy": acc, "n_samples": float(len(features))}
