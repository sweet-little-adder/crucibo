"""US equities live runtime — order SM, recon, RTH, dry-run broker (no network)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bar_ticks import make_price_series_ticks
from crucibo.live.account import LocalAccount
from crucibo.live.budgets import LatencyBudget
from crucibo.live.clock import SessionClock
from crucibo.live.equity_broker import DryRunEquityBroker, build_equity_broker
from crucibo.live.orders import OrderBook, OrderPhase
from crucibo.live.reconcile import BrokerSnapshot, reconcile_account
from crucibo.live.runtime import LiveEquityConfig, LiveEquityRuntime, run_live_equities_session
from crucibo.paper.engine import PaperConfig
from crucibo.replay.strategies import AlwaysFlat, BuyAndHold


def _rth_ns(hour: int = 10, minute: int = 0) -> int:
    """A Wednesday 2024-06-05 in America/New_York → UTC ns."""
    ny = ZoneInfo("America/New_York")
    dt = datetime(2024, 6, 5, hour, minute, tzinfo=ny)
    return int(dt.astimezone(UTC).timestamp() * 1_000_000_000)


def test_session_clock_rth() -> None:
    clock = SessionClock()
    assert clock.is_rth(_rth_ns(10, 0))
    assert not clock.is_rth(_rth_ns(8, 0))
    assert not clock.is_rth(_rth_ns(17, 0))


def test_order_book_transitions() -> None:
    from crucibo.live.broker import OrderIntent, OrderResult, OrderSide, OrderStatus

    book = OrderBook()
    intent = OrderIntent(
        client_order_id="c1",
        symbol="AAPL",
        side=OrderSide.BUY,
        qty_shares=10,
        mark_price=100.0,
        ts_event_ns=1,
    )
    mo = book.register(intent)
    assert mo.phase == OrderPhase.NEW
    book.apply(
        OrderResult(
            client_order_id="c1",
            status=OrderStatus.FILLED,
            filled_qty=10,
            exec_price=100.1,
        )
    )
    assert mo.phase == OrderPhase.FILLED


def test_reconcile_detects_drift() -> None:
    local = LocalAccount(cash=1000.0)
    local.apply_fill(symbol="AAPL", side="BUY", qty=5, price=100.0, fee=0.0)
    snap = BrokerSnapshot(cash=1000.0, positions={"AAPL": 0}, source="test")
    diff = reconcile_account(local, snap)
    assert not diff.ok
    assert "AAPL" in diff.position_deltas


def test_latency_budget_enforce() -> None:
    b = LatencyBudget(name="decision", warn_ns=10, kill_ns=100, enforce=True)
    assert b.observe(50) is None
    assert b.observe(200) is not None
    assert b.summary()["violation_count"] == 1


def test_dry_run_equity_broker_roundtrip() -> None:
    br = DryRunEquityBroker(cash=10_000.0, slip_bps=0.0, fee_per_share=0.0)
    from crucibo.live.broker import OrderIntent, OrderSide, OrderStatus

    buy = OrderIntent(
        client_order_id="b1",
        symbol="AAPL",
        side=OrderSide.BUY,
        qty_shares=10,
        mark_price=100.0,
        ts_event_ns=1,
        mode="live_equities",
    )
    r = br.submit(buy)
    assert r.status == OrderStatus.FILLED
    assert br.positions["AAPL"] == 10
    snap = br.snapshot(symbol="AAPL")
    assert snap.positions["AAPL"] == 10


def test_live_equities_runtime_buy_and_recon(tmp_path: Path) -> None:
    ticks = []
    for i, px in enumerate([100.0, 101.0, 102.0]):
        base = make_price_series_ticks(n=1, start_price=px, step=0.0)[0]
        ticks.append(
            base.model_copy(
                update={
                    "symbol": "AAPL",
                    "ts_event_ns": _rth_ns(10, i),
                    "ts_ingest_ns": _rth_ns(10, i) + 1_000_000,
                    "price": px,
                }
            )
        )

    async def _stream():
        for t in ticks:
            yield t

    paper = PaperConfig(
        initial_cash=50_000.0,
        slip_bps=0.0,
        fee_per_share=0.0,
        max_loss_usd=5_000.0,
        max_notional_usd=20_000.0,
    )
    broker = DryRunEquityBroker(cash=paper.initial_cash, slip_bps=0.0, fee_per_share=0.0)
    runtime = LiveEquityRuntime(
        broker=broker,
        cfg=LiveEquityConfig(
            paper=paper,
            rth_only=True,
            reconcile_every_n=1,
            kill_on_reconcile_fail=True,
        ),
    )
    strat = BuyAndHold(target_shares=5)

    async def _run():
        return await run_live_equities_session(
            runtime=runtime,
            strategy=strat,
            tick_stream=_stream(),
        )

    state = asyncio.run(_run())
    assert state.tick_count == 3
    assert state.account.position_shares("AAPL") == 5
    assert not state.killed
    assert state.last_reconcile is not None
    assert state.last_reconcile["ok"] is True
    assert len(state.order_book.orders) >= 1
    assert len(state.equity_curve) == 3


def test_rth_only_skips_orders_outside_session() -> None:
    off_hours = make_price_series_ticks(n=1, start_price=100.0, step=0.0)[0].model_copy(
        update={"symbol": "AAPL", "ts_event_ns": _rth_ns(7, 0), "price": 100.0}
    )

    async def _stream():
        yield off_hours

    paper = PaperConfig(initial_cash=10_000.0, max_loss_usd=1_000.0)
    broker = DryRunEquityBroker(cash=paper.initial_cash)
    runtime = LiveEquityRuntime(
        broker=broker,
        cfg=LiveEquityConfig(paper=paper, rth_only=True, reconcile_every_n=0),
    )

    async def _run():
        return await run_live_equities_session(
            runtime=runtime,
            strategy=BuyAndHold(target_shares=3),
            tick_stream=_stream(),
            max_ticks=1,
        )

    state = asyncio.run(_run())
    assert state.account.position_shares("AAPL") == 0
    assert len(state.order_book.orders) == 0


def test_build_equity_broker_dry_run() -> None:
    b = build_equity_broker(kind="dry_run", initial_cash=1_000.0)
    assert b.name == "dry_run"


def test_alpaca_broker_with_mock_transport() -> None:
    """Signed path without network: inject httpx mock transport."""
    import httpx

    from crucibo.live.broker import OrderIntent, OrderSide, OrderStatus
    from crucibo.live.equity_broker import AlpacaPaperBroker

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/orders" and request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "id": "ord-1",
                    "status": "filled",
                    "filled_qty": "2",
                    "filled_avg_price": "150.25",
                    "symbol": "AAPL",
                },
            )
        if request.url.path == "/v2/account":
            return httpx.Response(200, json={"cash": "100000"})
        if request.url.path.startswith("/v2/positions"):
            return httpx.Response(200, json={"symbol": "AAPL", "qty": "2"})
        return httpx.Response(404, json={"message": "not found"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(
        base_url="https://paper-api.alpaca.markets",
        transport=transport,
        headers={"APCA-API-KEY-ID": "k", "APCA-API-SECRET-KEY": "s"},
    )
    br = AlpacaPaperBroker(api_key="k", api_secret="s", client=client)
    result = br.submit(
        OrderIntent(
            client_order_id="cli-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            qty_shares=2,
            mark_price=150.0,
            ts_event_ns=1,
            mode="live_equities",
        )
    )
    assert result.status == OrderStatus.FILLED
    assert result.filled_qty == 2
    assert result.exec_price == pytest.approx(150.25)
    snap = br.snapshot(symbol="AAPL")
    assert snap.positions.get("AAPL") == 2
    br.close()


def test_flat_strategy_no_orders() -> None:
    tick = make_price_series_ticks(n=1, start_price=50.0, step=0.0)[0].model_copy(
        update={"symbol": "MSFT", "ts_event_ns": _rth_ns(11, 0)}
    )

    async def _stream():
        yield tick

    paper = PaperConfig(initial_cash=5_000.0, max_notional_usd=1_000.0)
    broker = DryRunEquityBroker(cash=paper.initial_cash)
    runtime = LiveEquityRuntime(
        broker=broker,
        cfg=LiveEquityConfig(paper=paper, rth_only=True, reconcile_every_n=0),
    )

    state = asyncio.run(
        run_live_equities_session(
            runtime=runtime,
            strategy=AlwaysFlat(),
            tick_stream=_stream(),
            max_ticks=1,
        )
    )
    assert state.order_book.orders == {}
