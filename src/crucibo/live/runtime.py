"""US equities live runtime — feed → risk → order SM → broker → recon."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from crucibo.live.account import LocalAccount
from crucibo.live.broker import OrderIntent, OrderSide, OrderStatus
from crucibo.live.budgets import BudgetBoard
from crucibo.live.clock import SessionClock
from crucibo.live.equity_broker import EquityBroker
from crucibo.live.latency import LatencyTracker
from crucibo.live.orders import OrderBook
from crucibo.live.reconcile import reconcile_account
from crucibo.live.risk import RiskLimits, check_pretrade
from crucibo.models import TradeTick, utc_now_ns
from crucibo.paper.engine import PaperConfig, PaperState
from crucibo.replay.strategies import TickStrategy


@dataclass
class LiveEquityConfig:
    """Stocks-first live loop configuration."""

    paper: PaperConfig
    rth_only: bool = True
    reconcile_every_n: int = 1
    kill_on_reconcile_fail: bool = True
    mode: str = "live_equities"  # live_equities | live_equities_dry
    enforce_latency_budgets: bool = False


@dataclass
class LiveEquityState:
    account: LocalAccount
    paper: PaperState
    order_book: OrderBook = field(default_factory=OrderBook)
    killed: bool = False
    kill_reason: str | None = None
    tick_count: int = 0
    last_reconcile: dict[str, object] | None = None
    reconcile_failures: int = 0
    equity_curve: list[dict[str, float | int | str]] = field(default_factory=list)


@dataclass
class LiveEquityRuntime:
    """
    Primary live path for **traditional US equities**.

    Crypto/Binance remains a separate optional paper feed — not this runtime.
    """

    broker: EquityBroker
    cfg: LiveEquityConfig
    clock: SessionClock = field(default_factory=SessionClock)
    latency: LatencyTracker = field(default_factory=LatencyTracker)
    budgets: BudgetBoard = field(default_factory=BudgetBoard)
    _order_seq: int = 0

    def __post_init__(self) -> None:
        if self.cfg.enforce_latency_budgets:
            self.budgets.decision.enforce = True
            self.budgets.tick_to_order.enforce = True

    def initial_state(self) -> LiveEquityState:
        cash = self.cfg.paper.initial_cash
        return LiveEquityState(
            account=LocalAccount(cash=cash, equity_peak=cash),
            paper=PaperState(cash=cash, equity_peak=cash),
        )

    def on_tick(
        self,
        *,
        strategy: TickStrategy,
        tick: TradeTick,
        state: LiveEquityState,
    ) -> LiveEquityState:
        if state.killed:
            return state

        if not self.clock.should_trade(tick.ts_event_ns, rth_only=self.cfg.rth_only):
            # Still mark equity outside RTH; no new orders
            eq = state.account.mark_equity({tick.symbol.upper(): tick.price})
            state.equity_curve.append(
                {
                    "ts_event_ns": tick.ts_event_ns,
                    "equity_marked": eq,
                    "cash": state.account.cash,
                    "shares": state.account.position_shares(tick.symbol),
                    "mid_price": tick.price,
                    "session": self.clock.label(tick.ts_event_ns),
                }
            )
            state.tick_count += 1
            return state

        t0 = self.latency.span_start()
        self.latency.record_feed_lag(ts_event_ns=tick.ts_event_ns, ts_ingest_ns=tick.ts_ingest_ns)
        if tick.ts_ingest_ns is not None and tick.ts_ingest_ns >= tick.ts_event_ns:
            kill = self.budgets.feed_lag.observe(
                int(tick.ts_ingest_ns - tick.ts_event_ns),
                context=tick.symbol,
            )
            if kill:
                state.killed = True
                state.kill_reason = kill
                return state

        sym = tick.symbol.upper()
        position = state.account.position_shares(sym)
        cash = state.account.cash
        equity = state.account.mark_equity({sym: tick.price})

        want = strategy.desired_shares(
            tick=tick,
            index=state.tick_count,
            n_ticks=state.tick_count + 1,
            position=position,
            cash=cash,
        )
        limits = RiskLimits(
            max_loss_usd=self.cfg.paper.max_loss_usd,
            max_position_shares=self.cfg.paper.max_position_shares,
            max_notional_usd=self.cfg.paper.max_notional_usd,
        )
        verdict = check_pretrade(
            target_shares=want,
            position=position,
            cash=cash,
            mark_price=tick.price,
            equity=equity,
            equity_peak=state.account.equity_peak,
            limits=limits,
        )
        decision_ns = self.latency.span_end(t0)
        self.latency.record_decision(decision_ns)
        kill = self.budgets.decision.observe(decision_ns, context=sym)
        if kill:
            state.killed = True
            state.kill_reason = kill
            return state

        if not verdict.ok and verdict.clamped_target is None:
            state.killed = True
            state.kill_reason = verdict.reason
            self._append_equity(state, tick, equity)
            state.tick_count += 1
            return state

        target = verdict.clamped_target if verdict.clamped_target is not None else want
        delta = target - position
        if delta != 0:
            self._order_seq += 1
            intent = OrderIntent(
                client_order_id=f"eq-{self._order_seq}-{tick.ts_event_ns}",
                symbol=sym,
                side=OrderSide.BUY if delta > 0 else OrderSide.SELL,
                qty_shares=abs(delta),
                mark_price=tick.price,
                ts_event_ns=tick.ts_event_ns,
                mode=self.cfg.mode,
            )
            managed = state.order_book.register(intent)
            t_ord = self.latency.span_start()
            result = self.broker.submit(intent)
            t2o = self.latency.span_end(t_ord)
            self.latency.record_tick_to_order(self.latency.span_end(t0))
            kill = self.budgets.tick_to_order.observe(t2o, context=sym)
            managed.apply_result(result)

            if result.status == OrderStatus.FILLED and result.exec_price is not None:
                try:
                    state.account.apply_fill(
                        symbol=sym,
                        side=intent.side.value,
                        qty=result.filled_qty,
                        price=result.exec_price,
                        fee=result.fee_cash,
                    )
                    state.paper.fills.append(
                        {
                            "ts_event_ns": tick.ts_event_ns,
                            "symbol": sym,
                            "side": intent.side.value,
                            "qty_shares": result.filled_qty,
                            "exec_price": result.exec_price,
                            "fee_cash": result.fee_cash,
                            "cash_after": state.account.cash,
                            "shares_after": state.account.position_shares(sym),
                            "mid_price_tick": tick.price,
                            "slip_bps": self.cfg.paper.slip_bps,
                        }
                    )
                except ValueError as exc:
                    state.killed = True
                    state.kill_reason = str(exc)
            elif result.status in {OrderStatus.REJECTED, OrderStatus.CANCELED}:
                # Rejection is not always a kill; kill on risk-related rejects
                if result.reason and "insufficient" in result.reason.lower():
                    state.killed = True
                    state.kill_reason = result.reason
            if kill:
                state.killed = True
                state.kill_reason = kill

        # Sync paper state mirror for bundle writers
        state.paper.cash = state.account.cash
        state.paper.shares = state.account.position_shares(sym)
        state.paper.equity_peak = state.account.equity_peak
        state.paper.killed = state.killed
        state.paper.kill_reason = state.kill_reason
        state.paper.last_mark_price = tick.price

        equity = state.account.mark_equity({sym: tick.price})
        # Drawdown kill
        if self.cfg.paper.max_loss_usd is not None:
            dd = state.account.equity_peak - equity
            if dd > self.cfg.paper.max_loss_usd + 1e-9:
                state.killed = True
                state.kill_reason = (
                    f"max_loss_usd exceeded: drawdown {dd:.2f} "
                    f"> {self.cfg.paper.max_loss_usd:.2f}"
                )
                state.paper.killed = True
                state.paper.kill_reason = state.kill_reason

        self._append_equity(state, tick, equity)
        state.tick_count += 1

        if (
            self.cfg.reconcile_every_n > 0
            and state.tick_count % self.cfg.reconcile_every_n == 0
        ):
            snap = self.broker.snapshot(symbol=sym)
            diff = reconcile_account(state.account, snap)
            state.last_reconcile = diff.to_dict()
            if not diff.ok:
                state.reconcile_failures += 1
                if self.cfg.kill_on_reconcile_fail:
                    state.killed = True
                    state.kill_reason = "reconcile failed: " + "; ".join(diff.reasons)
                    state.paper.killed = True
                    state.paper.kill_reason = state.kill_reason

        # Flatten on kill if configured
        if state.killed and self.cfg.paper.flatten_on_kill:
            held = state.account.position_shares(sym)
            if held > 0:
                self._order_seq += 1
                intent = OrderIntent(
                    client_order_id=f"eq-flat-{self._order_seq}-{utc_now_ns()}",
                    symbol=sym,
                    side=OrderSide.SELL,
                    qty_shares=held,
                    mark_price=tick.price,
                    ts_event_ns=tick.ts_event_ns,
                    mode=self.cfg.mode,
                )
                state.order_book.register(intent)
                result = self.broker.submit(intent)
                state.order_book.apply(result)
                if result.status == OrderStatus.FILLED and result.exec_price is not None:
                    try:
                        state.account.apply_fill(
                            symbol=sym,
                            side="SELL",
                            qty=result.filled_qty,
                            price=result.exec_price,
                            fee=result.fee_cash,
                        )
                    except ValueError:
                        pass
                state.paper.shares = state.account.position_shares(sym)
                state.paper.cash = state.account.cash

        return state

    def _append_equity(self, state: LiveEquityState, tick: TradeTick, equity: float) -> None:
        point = {
            "ts_event_ns": tick.ts_event_ns,
            "equity_marked": equity,
            "cash": state.account.cash,
            "shares": state.account.position_shares(tick.symbol),
            "mid_price": tick.price,
            "session": self.clock.label(tick.ts_event_ns),
            "drawdown": max(0.0, state.account.equity_peak - equity),
        }
        state.equity_curve.append(point)
        state.paper.equity_curve.append(
            {
                "ts_event_ns": tick.ts_event_ns,
                "equity_marked": equity,
                "cash": state.account.cash,
                "shares": state.account.position_shares(tick.symbol),
                "mid_price": tick.price,
                "drawdown": max(0.0, state.account.equity_peak - equity),
            }
        )


async def run_live_equities_session(
    *,
    runtime: LiveEquityRuntime,
    strategy: TickStrategy,
    tick_stream: AsyncIterator[TradeTick],
    max_ticks: int | None = None,
) -> LiveEquityState:
    state = runtime.initial_state()
    async for tick in tick_stream:
        state = runtime.on_tick(strategy=strategy, tick=tick, state=state)
        if state.killed:
            break
        if max_ticks is not None and state.tick_count >= max_ticks:
            break
    return state
