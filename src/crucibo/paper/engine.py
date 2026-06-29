"""Paper (simulated) execution — virtual fills, kill switch, no broker orders."""

from __future__ import annotations

from dataclasses import dataclass, field

from crucibo.models import TradeTick
from crucibo.replay.strategies import TickStrategy


@dataclass
class PaperConfig:
    initial_cash: float = 1_000_000.0
    slip_bps: float = 2.0
    fee_per_share: float = 0.005
    max_loss_usd: float | None = None
    max_position_shares: int | None = None


@dataclass
class PaperState:
    cash: float
    shares: int = 0
    fills: list[dict[str, float | int | str]] = field(default_factory=list)
    equity_peak: float = 0.0
    killed: bool = False
    kill_reason: str | None = None

    def equity_at(self, price: float) -> float:
        return self.cash + self.shares * price


def apply_tick(
    *,
    strategy: TickStrategy,
    tick: TradeTick,
    index: int,
    n_ticks: int,
    cfg: PaperConfig,
    state: PaperState,
) -> PaperState:
    if state.killed:
        return state

    want = strategy.desired_shares(
        tick=tick,
        index=index,
        n_ticks=n_ticks,
        position=state.shares,
        cash=state.cash,
    )
    if cfg.max_position_shares is not None:
        want = min(want, cfg.max_position_shares)
    if want < 0:
        raise ValueError("negative target shares not supported in paper engine")

    slip_m = cfg.slip_bps / 10_000.0
    delta = want - state.shares
    fills = list(state.fills)
    cash = state.cash
    shares = state.shares

    if delta != 0:
        if delta > 0:
            exec_px = tick.price * (1.0 + slip_m)
            gross = delta * exec_px
            fee = delta * cfg.fee_per_share
            total = gross + fee
            if total > cash + 1e-9:
                state.killed = True
                state.kill_reason = f"insufficient cash: need {total:.2f} have {cash:.2f}"
                return state
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

    equity = cash + shares * tick.price
    peak = max(state.equity_peak, equity)
    killed = state.killed
    reason = state.kill_reason
    if cfg.max_loss_usd is not None:
        drawdown = peak - equity
        if drawdown > cfg.max_loss_usd + 1e-9:
            killed = True
            reason = f"max_loss_usd exceeded: drawdown {drawdown:.2f} > {cfg.max_loss_usd:.2f}"

    return PaperState(
        cash=cash,
        shares=shares,
        fills=fills,
        equity_peak=peak,
        killed=killed,
        kill_reason=reason,
    )
