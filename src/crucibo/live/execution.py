"""Execution backends — paper and live dry-run share the same rebalance shape."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from crucibo.live.broker import DryRunBroker, OrderIntent, OrderSide
from crucibo.live.latency import LatencyTracker
from crucibo.live.risk import RiskLimits, check_pretrade
from crucibo.models import TradeTick
from crucibo.paper.engine import PaperConfig, PaperState, apply_tick
from crucibo.replay.strategies import TickStrategy


class ExecutionBackend(Protocol):
    """Strategy → risk → fill path. Live broker will implement the same surface."""

    def on_tick(
        self,
        *,
        strategy: TickStrategy,
        tick: TradeTick,
        index: int,
        n_ticks: int,
        state: PaperState,
    ) -> PaperState: ...


class _FixedTarget:
    def __init__(self, shares: int) -> None:
        self._shares = shares

    def desired_shares(self, **_kwargs: object) -> int:
        return self._shares


@dataclass
class PaperExecutionBackend:
    """Delegates to paper apply_tick (virtual fills)."""

    cfg: PaperConfig
    latency: LatencyTracker | None = None

    def on_tick(
        self,
        *,
        strategy: TickStrategy,
        tick: TradeTick,
        index: int,
        n_ticks: int,
        state: PaperState,
    ) -> PaperState:
        if self.latency is not None:
            self.latency.record_feed_lag(
                ts_event_ns=tick.ts_event_ns,
                ts_ingest_ns=tick.ts_ingest_ns,
            )
            t0 = self.latency.span_start()
            state = apply_tick(
                strategy=strategy,
                tick=tick,
                index=index,
                n_ticks=n_ticks,
                cfg=self.cfg,
                state=state,
            )
            self.latency.record_decision(self.latency.span_end(t0))
            return state
        return apply_tick(
            strategy=strategy,
            tick=tick,
            index=index,
            n_ticks=n_ticks,
            cfg=self.cfg,
            state=state,
        )


@dataclass
class DryRunLiveBackend:
    """
    Live-shaped path without real capital: pre-trade risk → DryRunBroker order
    intents → same virtual fill economics as paper.
    """

    cfg: PaperConfig
    broker: DryRunBroker
    mode: str = "live_dry_run"
    latency: LatencyTracker | None = None
    _order_seq: int = 0

    def on_tick(
        self,
        *,
        strategy: TickStrategy,
        tick: TradeTick,
        index: int,
        n_ticks: int,
        state: PaperState,
    ) -> PaperState:
        if state.killed:
            return state

        tracker = self.latency
        t0 = tracker.span_start() if tracker is not None else None
        if tracker is not None:
            tracker.record_feed_lag(ts_event_ns=tick.ts_event_ns, ts_ingest_ns=tick.ts_ingest_ns)

        want = strategy.desired_shares(
            tick=tick,
            index=index,
            n_ticks=n_ticks,
            position=state.shares,
            cash=state.cash,
        )
        equity = state.equity_at(tick.price)
        verdict = check_pretrade(
            target_shares=want,
            position=state.shares,
            cash=state.cash,
            mark_price=tick.price,
            equity=equity,
            equity_peak=max(state.equity_peak, equity),
            limits=RiskLimits(
                max_loss_usd=self.cfg.max_loss_usd,
                max_position_shares=self.cfg.max_position_shares,
                max_notional_usd=self.cfg.max_notional_usd,
            ),
        )

        if not verdict.ok and verdict.clamped_target is None:
            # Hard kill (e.g. max loss): hold position for this tick, then freeze.
            state = apply_tick(
                strategy=_FixedTarget(state.shares),
                tick=tick,
                index=index,
                n_ticks=n_ticks,
                cfg=self.cfg,
                state=state,
            )
            state.killed = True
            state.kill_reason = verdict.reason
            if tracker is not None and t0 is not None:
                tracker.record_decision(tracker.span_end(t0))
            return state

        target = verdict.clamped_target if verdict.clamped_target is not None else want
        delta = target - state.shares
        if delta != 0:
            self._order_seq += 1
            intent = OrderIntent(
                client_order_id=f"dry-{self._order_seq}-{tick.ts_event_ns}",
                symbol=tick.symbol,
                side=OrderSide.BUY if delta > 0 else OrderSide.SELL,
                qty_shares=abs(delta),
                mark_price=tick.price,
                ts_event_ns=tick.ts_event_ns,
                mode=self.mode,
            )
            self.broker.submit(intent)
            if tracker is not None and t0 is not None:
                tracker.record_tick_to_order(tracker.span_end(t0))

        state = apply_tick(
            strategy=_FixedTarget(target),
            tick=tick,
            index=index,
            n_ticks=n_ticks,
            cfg=self.cfg,
            state=state,
        )
        if tracker is not None and t0 is not None:
            tracker.record_decision(tracker.span_end(t0))
        return state


def rebalance_to_target(
    *,
    state: PaperState,
    tick: TradeTick,
    target: int,
    cfg: PaperConfig,
    index: int = 0,
) -> PaperState:
    """Helper for tests / live bridge: rebalance without a full strategy object."""
    return apply_tick(
        strategy=_FixedTarget(target),
        tick=tick,
        index=index,
        n_ticks=index + 1,
        cfg=cfg,
        state=state,
    )
