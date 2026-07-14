"""Paper dashboard HTTP surface (no Binance network)."""

from __future__ import annotations

import asyncio

from bar_ticks import make_price_series_ticks
from crucibo.paper.dashboard import INDEX_HTML, DashboardMeta, EventHub, tick_snapshot
from crucibo.paper.engine import PaperState


def test_index_html_packaged() -> None:
    assert INDEX_HTML.is_file()
    body = INDEX_HTML.read_text(encoding="utf-8")
    assert "crucibo paper" in body
    assert "/events" in body


def test_tick_snapshot_fields() -> None:
    ticks = make_price_series_ticks(n=1, start_price=100.0)
    tick = ticks[0]
    state = PaperState(cash=1_000_000.0, shares=2, equity_peak=1_000_200.0)
    meta = DashboardMeta(
        feed="alphavantage",
        symbol="AAPL",
        interval="5min",
        strategy="aapl_mlp_v1",
        model_path="/tmp/artifact",
        initial_cash=1_000_000.0,
    )
    snap = tick_snapshot(tick=tick, state=state, tick_index=1, meta=meta, fill=None)
    assert snap["symbol"] == tick.symbol
    assert snap["feed"] == "alphavantage"
    assert snap["interval"] == "5min"
    assert snap["equity"] == 1_000_200.0
    assert snap["pnl"] == 200.0


def test_dashboard_serves_index() -> None:
    from crucibo.paper.dashboard import _handle_http_client

    async def _run() -> None:
        hub = EventHub()
        server = await asyncio.start_server(
            lambda r, w: _handle_http_client(r, w, hub),
            host="127.0.0.1",
            port=0,
        )
        port = server.sockets[0].getsockname()[1]
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
            await writer.drain()
            head = await reader.readuntil(b"\r\n\r\n")
            body = await reader.read()
            writer.close()
            await writer.wait_closed()

            assert b"200 OK" in head
            assert b"text/html" in head
            assert b"crucibo paper" in body
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(_run())