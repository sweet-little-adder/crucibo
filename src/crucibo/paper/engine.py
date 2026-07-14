"""Paper (simulated) execution — virtual fills, kill switch, no broker orders."""

from __future__ import annotations

from dataclasses import dataclass, field

from crucibo.models import TradeTick, utc_now_ns
from crucibo.replay.strategies import TickStrategy


@dataclass
class PaperConfig:
    initial_cash: float = 1_000_000.0
    slip_bps: float = 2.0
    fee_per_share: float = 0.005
    max_loss_usd: float | None = None
    max_position_shares: int | None = None
    max_notional_usd: float | None = None
    flatten_on_kill: bool = False


@dataclass
class PaperState:
    cash: float
    shares: int = 0
    fills: list[dict[str, float | int | str]] = field(default_factory=list)
    equity_curve: list[dict[str, float | int]] = field(default_factory=list)
    latency_samples_ns: list[int] = field(default_factory=list)
    decision_latencies_ns: list[int] = field(default_factory=list)
    equity_peak: float = 0.0
    killed: bool = False
    kill_reason: str | None = None
    last_mark_price: float | None = None

    def equity_at(self, price: float) -> float:
        return self.cash + self.shares * price


def _clamp_want(
    want: int,
    *,
    price: float,
    cash: float,
    cfg: PaperConfig,
) -> int:
    if want < 0:
        raise ValueError("negative target shares not supported in paper engine")
    if cfg.max_position_shares is not None:
        want = min(want, cfg.max_position_shares)
    if cfg.max_notional_usd is not None and price > 0:
        max_shares = int(cfg.max_notional_usd // price)
        want = min(want, max_shares)
    # Cannot buy more than cash allows (pre-check; still kill if fees push over)
    if want > 0 and price > 0:
        affordable = int(cash // price)
        if want > affordable and affordable >= 0:
            # leave kill to insufficient cash on actual order only if fees cause overflow
            pass
    return want


def _virtual_fill(
    *,
    state: PaperState,
    tick: TradeTick,
    want: int,
    cfg: PaperConfig,
) -> PaperState:
    slip_m = cfg.slip_bps / 10_000.0
    delta = want - state.shares
    fills = list(state.fills)
    cash = state.cash
    shares = state.shares

    if delta == 0:
        return PaperState(
            cash=cash,
            shares=shares,
            fills=fills,
            equity_curve=list(state.equity_curve),
            latency_samples_ns=list(state.latency_samples_ns),
            decision_latencies_ns=list(state.decision_latencies_ns),
            equity_peak=state.equity_peak,
            killed=state.killed,
            kill_reason=state.kill_reason,
            last_mark_price=tick.price,
        )

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
            "mid_price_tick": tick.price,
            "slip_bps": cfg.slip_bps,
        }
    )
    return PaperState(
        cash=cash,
        shares=shares,
        fills=fills,
        equity_curve=list(state.equity_curve),
        latency_samples_ns=list(state.latency_samples_ns),
        decision_latencies_ns=list(state.decision_latencies_ns),
        equity_peak=state.equity_peak,
        killed=state.killed,
        kill_reason=state.kill_reason,
        last_mark_price=tick.price,
    )


def _maybe_kill_drawdown(state: PaperState, *, equity: float, cfg: PaperConfig) -> PaperState:
    peak = max(state.equity_peak, equity)
    killed = state.killed
    reason = state.kill_reason
    if cfg.max_loss_usd is not None:
        drawdown = peak - equity
        if drawdown > cfg.max_loss_usd + 1e-9:
            killed = True
            reason = f"max_loss_usd exceeded: drawdown {drawdown:.2f} > {cfg.max_loss_usd:.2f}"
    return PaperState(
        cash=state.cash,
        shares=state.shares,
        fills=list(state.fills),
        equity_curve=list(state.equity_curve),
        latency_samples_ns=list(state.latency_samples_ns),
        decision_latencies_ns=list(state.decision_latencies_ns),
        equity_peak=peak,
        killed=killed,
        kill_reason=reason,
        last_mark_price=state.last_mark_price,
    )


def _append_equity_point(state: PaperState, *, tick: TradeTick, equity: float) -> PaperState:
    curve = list(state.equity_curve)
    curve.append(
        {
            "ts_event_ns": tick.ts_event_ns,
            "equity_marked": equity,
            "cash": state.cash,
            "shares": state.shares,
            "mid_price": tick.price,
            "drawdown": max(0.0, state.equity_peak - equity),
        }
    )
    return PaperState(
        cash=state.cash,
        shares=state.shares,
        fills=list(state.fills),
        equity_curve=curve,
        latency_samples_ns=list(state.latency_samples_ns),
        decision_latencies_ns=list(state.decision_latencies_ns),
        equity_peak=state.equity_peak,
        killed=state.killed,
        kill_reason=state.kill_reason,
        last_mark_price=tick.price,
    )


def _record_latency(state: PaperState, tick: TradeTick, decision_ns: int) -> PaperState:
    samples = list(state.latency_samples_ns)
    decisions = list(state.decision_latencies_ns)
    if tick.ts_ingest_ns is not None and tick.ts_ingest_ns >= tick.ts_event_ns:
        samples.append(int(tick.ts_ingest_ns - tick.ts_event_ns))
    decisions.append(decision_ns)
    return PaperState(
        cash=state.cash,
        shares=state.shares,
        fills=list(state.fills),
        equity_curve=list(state.equity_curve),
        latency_samples_ns=samples,
        decision_latencies_ns=decisions,
        equity_peak=state.equity_peak,
        killed=state.killed,
        kill_reason=state.kill_reason,
        last_mark_price=state.last_mark_price,
    )


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

    t0 = utc_now_ns()
    want = strategy.desired_shares(
        tick=tick,
        index=index,
        n_ticks=n_ticks,
        position=state.shares,
        cash=state.cash,
    )
    want = _clamp_want(want, price=tick.price, cash=state.cash, cfg=cfg)
    decision_ns = utc_now_ns() - t0

    state = _virtual_fill(state=state, tick=tick, want=want, cfg=cfg)
    if state.killed and not cfg.flatten_on_kill:
        equity = state.equity_at(tick.price)
        state = _maybe_kill_drawdown(state, equity=equity, cfg=cfg)
        state = _append_equity_point(state, tick=tick, equity=state.equity_at(tick.price))
        return _record_latency(state, tick, decision_ns)

    # Flatten after kill if configured (e.g. max-loss) — only when position open
    equity = state.equity_at(tick.price)
    state = _maybe_kill_drawdown(state, equity=equity, cfg=cfg)
    if state.killed and cfg.flatten_on_kill and state.shares != 0:
        flat_cfg = PaperConfig(
            initial_cash=cfg.initial_cash,
            slip_bps=cfg.slip_bps,
            fee_per_share=cfg.fee_per_share,
            max_loss_usd=None,
            max_position_shares=None,
            max_notional_usd=None,
            flatten_on_kill=False,
        )
        # Clear kill only for flatten fill path, then restore kill flags
        reason = state.kill_reason
        state.killed = False
        state.kill_reason = None
        state = _virtual_fill(state=state, tick=tick, want=0, cfg=flat_cfg)
        state.killed = True
        state.kill_reason = reason

    equity = state.equity_at(tick.price)
    state = _maybe_kill_drawdown(state, equity=equity, cfg=cfg)
    # peak already updated; re-read equity after possible flatten
    equity = state.equity_at(tick.price)
    state = _append_equity_point(state, tick=tick, equity=equity)
    return _record_latency(state, tick, decision_ns)


def latency_summary(state: PaperState) -> dict[str, float | int | None]:
    """Aggregate feed lag and decision-path latency for manifests."""

    def _stats(samples: list[int]) -> dict[str, float | int | None]:
        if not samples:
            return {"count": 0, "mean_ns": None, "p50_ns": None, "p99_ns": None, "max_ns": None}
        ordered = sorted(samples)
        n = len(ordered)
        mean = sum(ordered) / n
        p50 = ordered[n // 2]
        p99 = ordered[min(n - 1, int(n * 0.99))]
        return {
            "count": n,
            "mean_ns": float(mean),
            "p50_ns": int(p50),
            "p99_ns": int(p99),
            "max_ns": int(ordered[-1]),
        }

    return {
        "feed_lag": _stats(state.latency_samples_ns),
        "decision": _stats(state.decision_latencies_ns),
    }
