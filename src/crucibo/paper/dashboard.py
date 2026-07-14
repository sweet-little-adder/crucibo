"""Minimal black-and-white web dashboard for live paper trading (SSE)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from crucibo.models import TradeTick
from crucibo.paper.engine import PaperConfig, PaperState
from crucibo.paper.session import (
    run_paper_alphavantage_session,
    run_paper_binance_session,
    write_paper_manifest,
)
from crucibo.replay.strategies import TickStrategy

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"


@dataclass(frozen=True)
class DashboardMeta:
    feed: str
    symbol: str
    interval: str
    strategy: str
    model_path: str | None
    initial_cash: float


def _ts_label(ts_event_ns: int) -> str:
    dt = datetime.fromtimestamp(ts_event_ns / 1_000_000_000, tz=UTC)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def tick_snapshot(
    *,
    tick: TradeTick,
    state: PaperState,
    tick_index: int,
    meta: DashboardMeta,
    fill: dict[str, float | int | str] | None,
) -> dict[str, object]:
    equity = state.equity_at(tick.price)
    pnl = equity - meta.initial_cash
    drawdown = state.equity_peak - equity
    return {
        "type": "tick",
        "tick_index": tick_index,
        "ts_event_ns": tick.ts_event_ns,
        "ts_label": _ts_label(tick.ts_event_ns),
        "feed": meta.feed,
        "symbol": tick.symbol,
        "interval": meta.interval,
        "strategy": meta.strategy,
        "model_path": meta.model_path,
        "price": tick.price,
        "shares": state.shares,
        "cash": round(state.cash, 2),
        "equity": round(equity, 2),
        "equity_peak": round(state.equity_peak, 2),
        "pnl": round(pnl, 2),
        "drawdown": round(drawdown, 2),
        "initial_cash": meta.initial_cash,
        "killed": state.killed,
        "kill_reason": state.kill_reason,
        "fills_count": len(state.fills),
        "fill": fill,
    }


class EventHub:
    """Broadcast SSE payloads to connected browsers."""

    def __init__(self) -> None:
        self._clients: set[asyncio.StreamWriter] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self, writer: asyncio.StreamWriter) -> None:
        async with self._lock:
            self._clients.add(writer)

    async def unsubscribe(self, writer: asyncio.StreamWriter) -> None:
        async with self._lock:
            self._clients.discard(writer)

    async def publish(self, payload: dict[str, object]) -> None:
        line = f"data: {json.dumps(payload, separators=(',', ':'))}\n\n".encode()
        async with self._lock:
            dead: list[asyncio.StreamWriter] = []
            for writer in self._clients:
                try:
                    writer.write(line)
                    await writer.drain()
                except (ConnectionError, OSError, asyncio.CancelledError):
                    dead.append(writer)
            for writer in dead:
                self._clients.discard(writer)

    @property
    def client_count(self) -> int:
        return len(self._clients)


async def _read_request_line(reader: asyncio.StreamReader) -> str:
    line = await reader.readline()
    return line.decode("utf-8", errors="replace").strip()


async def _drain_headers(reader: asyncio.StreamReader) -> None:
    while True:
        line = await reader.readline()
        if line in (b"\r\n", b"\n", b""):
            break


def _http_response(
    *,
    status: int = 200,
    reason: str = "OK",
    headers: list[tuple[str, str]] | None = None,
    body: bytes = b"",
) -> bytes:
    hdrs = headers or []
    if body and not any(k.lower() == "content-length" for k, _ in hdrs):
        hdrs = [*hdrs, ("Content-Length", str(len(body)))]
    block = [f"HTTP/1.1 {status} {reason}"]
    block.extend(f"{k}: {v}" for k, v in hdrs)
    block.append("")
    head = "\r\n".join(block).encode() + b"\r\n"
    return head + body


async def _handle_http_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    hub: EventHub,
) -> None:
    try:
        request_line = await _read_request_line(reader)
        await _drain_headers(reader)
        parts = request_line.split()
        if len(parts) < 2:
            writer.write(_http_response(status=400, reason="Bad Request", body=b"bad request"))
            await writer.drain()
            return

        method, path = parts[0], parts[1]
        if method != "GET":
            writer.write(_http_response(status=405, reason="Method Not Allowed", body=b"GET only"))
            await writer.drain()
            return

        if path in {"/", "/index.html"}:
            body = INDEX_HTML.read_bytes()
            writer.write(
                _http_response(
                    headers=[("Content-Type", "text/html; charset=utf-8")],
                    body=body,
                )
            )
            await writer.drain()
            return

        if path == "/events":
            writer.write(
                _http_response(
                    headers=[
                        ("Content-Type", "text/event-stream"),
                        ("Cache-Control", "no-cache"),
                        ("Connection", "keep-alive"),
                    ],
                )
            )
            await writer.drain()
            await hub.subscribe(writer)
            try:
                while True:
                    writer.write(b": keepalive\n\n")
                    await writer.drain()
                    await asyncio.sleep(15)
            finally:
                await hub.unsubscribe(writer)
            return

        writer.write(_http_response(status=404, reason="Not Found", body=b"not found"))
        await writer.drain()
    except (asyncio.CancelledError, ConnectionError, OSError):
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except OSError:
            pass


async def run_paper_dashboard(
    *,
    strategy: TickStrategy,
    feed: str,
    symbol: str,
    interval: str,
    strategy_name: str,
    model_path: Path | None,
    cfg: PaperConfig,
    host: str = "127.0.0.1",
    port: int = 8765,
    poll_seconds: float = 300.0,
    max_ticks: int | None = None,
    runs_parent: Path | None = None,
    run_id: str | None = None,
    mode: str = "paper",
    backend=None,
    broker=None,
    latency=None,
) -> PaperState:
    """Run paper session and stream state to browsers at http://host:port/."""
    from crucibo.replay.bundle import default_runs_parent, make_run_id

    hub = EventHub()
    feed_key = feed.strip().lower()
    meta = DashboardMeta(
        feed=feed_key,
        symbol=symbol.upper(),
        interval=interval,
        strategy=strategy_name,
        model_path=str(model_path.resolve()) if model_path else None,
        initial_cash=cfg.initial_cash,
    )

    server = await asyncio.start_server(
        lambda r, w: _handle_http_client(r, w, hub),
        host=host,
        port=port,
    )

    tick_count = 0
    last_fill_count = 0
    state: PaperState | None = None

    async def _on_tick(tick: TradeTick, paper_state: PaperState) -> None:
        nonlocal tick_count, last_fill_count
        fill = None
        if len(paper_state.fills) > last_fill_count:
            fill = paper_state.fills[-1]
            last_fill_count = len(paper_state.fills)
        tick_count += 1
        await hub.publish(
            tick_snapshot(
                tick=tick,
                state=paper_state,
                tick_index=tick_count,
                meta=meta,
                fill=fill,
            )
        )

    async def _on_poll(payload: dict[str, object]) -> None:
        await hub.publish(payload)

    await hub.publish(
        {
            "type": "session",
            "feed": meta.feed,
            "mode": mode,
            "symbol": meta.symbol,
            "interval": meta.interval,
            "strategy": meta.strategy,
            "model_path": meta.model_path,
            "initial_cash": meta.initial_cash,
            "cash": meta.initial_cash,
            "shares": 0,
            "equity": meta.initial_cash,
            "pnl": 0.0,
            "drawdown": 0.0,
            "ticks": 0,
            "poll_seconds": poll_seconds if feed_key == "alphavantage" else None,
            "dashboard_url": f"http://{host}:{port}/",
            "message": (
                "Paper session is one Python process (not shell commands, not a Cursor agent). "
                "Waiting for new market bars before making decisions."
            ),
        }
    )

    try:
        if feed_key == "alphavantage":
            state = await run_paper_alphavantage_session(
                strategy=strategy,
                symbol=meta.symbol,
                interval=interval,
                cfg=cfg,
                poll_seconds=poll_seconds,
                max_ticks=max_ticks,
                on_tick=_on_tick,
                on_poll=_on_poll,
                backend=backend,
            )
        elif feed_key == "binance":
            state = await run_paper_binance_session(
                strategy=strategy,
                symbol=meta.symbol,
                interval=interval,
                cfg=cfg,
                max_ticks=max_ticks,
                on_tick=_on_tick,
                backend=backend,
            )
        else:
            raise ValueError(f"unknown feed: {feed!r} (try alphavantage | binance)")
    finally:
        await hub.publish(
            {
                "type": "done",
                "tick_count": tick_count,
                "killed": state.killed if state is not None else False,
                "kill_reason": state.kill_reason if state is not None else None,
                "final_cash": round(state.cash, 2) if state is not None else None,
                "final_shares": state.shares if state is not None else None,
            }
        )
        server.close()
        await server.wait_closed()

    if state is None:
        raise RuntimeError("paper session ended before producing state")

    parent = runs_parent or default_runs_parent()
    rid = run_id or make_run_id(prefix="paper", symbol=meta.symbol, strategy=strategy_name)
    extra = {}
    if latency is not None:
        extra["latency_tracker"] = latency.summary()
    write_paper_manifest(
        run_id=rid,
        runs_parent=parent,
        feed=meta.feed,
        symbol=meta.symbol,
        interval=interval,
        strategy_name=strategy_name,
        model_path=meta.model_path,
        cfg=cfg,
        state=state,
        tick_count=tick_count,
        poll_seconds=poll_seconds if feed_key == "alphavantage" else None,
        mode=mode,
        order_log=broker.order_log if broker is not None else None,
        extra_manifest=extra or None,
    )
    return state