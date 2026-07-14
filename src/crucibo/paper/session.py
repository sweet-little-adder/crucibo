"""Async paper-trading sessions on live bar streams."""

from __future__ import annotations

import inspect
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from crucibo.models import TradeTick
from crucibo.paper.alphavantage_poll import OnPoll, stream_new_alphavantage_bars
from crucibo.paper.binance_ws import stream_closed_klines
from crucibo.paper.bundle import write_paper_run_bundle
from crucibo.paper.engine import PaperConfig, PaperState
from crucibo.replay.strategies import TickStrategy

if TYPE_CHECKING:
    from crucibo.live.broker import DryRunBroker
    from crucibo.live.execution import ExecutionBackend
    from crucibo.live.latency import LatencyTracker

OnTick = Callable[[TradeTick, PaperState], Awaitable[None] | None]


@dataclass
class PaperSessionResult:
    state: PaperState
    tick_count: int
    interrupted: bool = False
    out_dir: Path | None = None
    mode: str = "paper"
    order_log: list[dict[str, object]] | None = None
    latency: dict | None = None


async def run_paper_session(
    *,
    strategy: TickStrategy,
    cfg: PaperConfig,
    tick_stream: AsyncIterator[TradeTick],
    max_ticks: int | None = None,
    on_tick: OnTick | None = None,
    backend: ExecutionBackend | None = None,
) -> PaperState:
    """Run until stream ends, kill, or max_ticks."""

    result = await run_paper_session_tracked(
        strategy=strategy,
        cfg=cfg,
        tick_stream=tick_stream,
        max_ticks=max_ticks,
        on_tick=on_tick,
        backend=backend,
    )
    return result.state


async def run_paper_session_tracked(
    *,
    strategy: TickStrategy,
    cfg: PaperConfig,
    tick_stream: AsyncIterator[TradeTick],
    max_ticks: int | None = None,
    on_tick: OnTick | None = None,
    backend: ExecutionBackend | None = None,
    mode: str = "paper",
) -> PaperSessionResult:
    if backend is None:
        from crucibo.live.execution import PaperExecutionBackend

        exec_backend: ExecutionBackend = PaperExecutionBackend(cfg=cfg)
    else:
        exec_backend = backend
    state = PaperState(cash=cfg.initial_cash, equity_peak=cfg.initial_cash)
    index = 0
    async for tick in tick_stream:
        state = exec_backend.on_tick(
            strategy=strategy,
            tick=tick,
            index=index,
            n_ticks=index + 1,
            state=state,
        )
        if on_tick is not None:
            maybe = on_tick(tick, state)
            if inspect.isawaitable(maybe):
                await maybe
        index += 1
        if state.killed:
            break
        if max_ticks is not None and index >= max_ticks:
            break
    return PaperSessionResult(state=state, tick_count=index, mode=mode)


async def run_paper_binance_session(
    *,
    strategy: TickStrategy,
    symbol: str,
    interval: str,
    cfg: PaperConfig,
    max_ticks: int | None = None,
    on_tick: OnTick | None = None,
    backend: ExecutionBackend | None = None,
) -> PaperState:
    stream = stream_closed_klines(symbol=symbol, interval=interval)
    return await run_paper_session(
        strategy=strategy,
        cfg=cfg,
        tick_stream=stream,
        max_ticks=max_ticks,
        on_tick=on_tick,
        backend=backend,
    )


async def run_paper_alphavantage_session(
    *,
    strategy: TickStrategy,
    symbol: str,
    interval: str,
    cfg: PaperConfig,
    poll_seconds: float = 300.0,
    max_ticks: int | None = None,
    on_tick: OnTick | None = None,
    on_poll: OnPoll | None = None,
    backend: ExecutionBackend | None = None,
) -> PaperState:
    stream = stream_new_alphavantage_bars(
        symbol=symbol,
        interval=interval,
        poll_seconds=poll_seconds,
        on_poll=on_poll,
    )
    return await run_paper_session(
        strategy=strategy,
        cfg=cfg,
        tick_stream=stream,
        max_ticks=max_ticks,
        on_tick=on_tick,
        backend=backend,
    )


def build_execution_backend(
    *,
    cfg: PaperConfig,
    mode: str = "paper",
) -> tuple[ExecutionBackend, DryRunBroker | None, LatencyTracker]:
    """Construct paper or live-dry-run backend + optional order-log broker."""

    from crucibo.live.broker import DryRunBroker
    from crucibo.live.execution import DryRunLiveBackend, PaperExecutionBackend
    from crucibo.live.latency import LatencyTracker

    latency = LatencyTracker()
    if mode == "live_dry_run":
        broker = DryRunBroker(slip_bps=cfg.slip_bps, fee_per_share=cfg.fee_per_share)
        backend: ExecutionBackend = DryRunLiveBackend(
            cfg=cfg,
            broker=broker,
            mode=mode,
            latency=latency,
        )
        return backend, broker, latency
    return PaperExecutionBackend(cfg=cfg, latency=latency), None, latency


def write_paper_manifest(
    *,
    out_dir: Path | None = None,
    symbol: str,
    interval: str,
    feed: str,
    strategy_name: str,
    model_path: str | None,
    cfg: PaperConfig,
    state: PaperState,
    tick_count: int,
    poll_seconds: float | None = None,
    mode: str = "paper",
    interrupted: bool = False,
    runs_parent: Path | None = None,
    run_id: str | None = None,
    order_log: list[dict[str, object]] | None = None,
    extra_manifest: dict | None = None,
) -> Path:
    """
    Write full bundle under ``data/runs/<run_id>/`` (fills, equity, manifest).

    Prefer ``run_id`` + ``runs_parent`` (data root). If only ``out_dir`` is given
    (legacy), treat ``out_dir.name`` as run_id and ``out_dir.parent`` as data root
    when parent is not already ``runs``.
    """
    if run_id is not None:
        rid = run_id
        parent = runs_parent
    elif out_dir is not None:
        rid = out_dir.name
        parent = out_dir.parent
        if parent.name == "runs":
            parent = parent.parent
    else:
        raise ValueError("write_paper_manifest requires run_id or out_dir")

    extra = dict(extra_manifest or {})
    if order_log is not None:
        extra["order_log_count"] = len(order_log)

    written = write_paper_run_bundle(
        run_id=rid,
        symbol=symbol,
        interval=interval,
        feed=feed,
        strategy_name=strategy_name,
        model_path=model_path,
        cfg=cfg,
        state=state,
        tick_count=tick_count,
        mode=mode,
        poll_seconds=poll_seconds,
        interrupted=interrupted,
        runs_parent=parent,
        extra_manifest=extra or None,
    )

    if order_log is not None:
        (written / "order_log.json").write_text(
            json.dumps(order_log, indent=2) + "\n",
            encoding="utf-8",
        )
    return written / "run_manifest.json"


def finalize_session_bundle(
    *,
    result: PaperSessionResult,
    symbol: str,
    interval: str,
    feed: str,
    strategy_name: str,
    model_path: str | None,
    cfg: PaperConfig,
    run_id: str,
    runs_parent: Path | None,
    poll_seconds: float | None = None,
    broker: DryRunBroker | None = None,
    latency: LatencyTracker | None = None,
) -> Path:
    """Write bundle after a session; merges latency tracker into manifest."""

    extra: dict = {}
    if latency is not None:
        extra["latency_tracker"] = latency.summary()
    order_log = broker.order_log if broker is not None else None
    path = write_paper_run_bundle(
        run_id=run_id,
        symbol=symbol,
        interval=interval,
        feed=feed,
        strategy_name=strategy_name,
        model_path=model_path,
        cfg=cfg,
        state=result.state,
        tick_count=result.tick_count,
        mode=result.mode,
        poll_seconds=poll_seconds,
        interrupted=result.interrupted,
        runs_parent=runs_parent,
        extra_manifest=extra or None,
    )
    if order_log is not None:
        (path / "order_log.json").write_text(
            json.dumps(order_log, indent=2) + "\n",
            encoding="utf-8",
        )
    result.out_dir = path
    result.order_log = order_log
    result.latency = extra.get("latency_tracker")
    return path
