"""Record replay sessions as dashboard-compatible show files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from crucibo.models import TradeTick
from crucibo.paper.dashboard import DashboardMeta, tick_snapshot
from crucibo.paper.engine import PaperConfig, PaperState, apply_tick
from crucibo.replay.strategies import TickStrategy

SHOW_SCHEMA_VERSION = 1
NY = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class ShowRecording:
    schema_version: int
    session: dict[str, object]
    events: list[dict[str, object]]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session": self.session,
            "events": self.events,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ShowRecording:
        version = int(data.get("schema_version", -1))
        if version != SHOW_SCHEMA_VERSION:
            raise ValueError(f"unsupported show schema_version: {version}")
        session = data.get("session")
        events = data.get("events")
        if not isinstance(session, dict):
            raise ValueError("show file missing session object")
        if not isinstance(events, list):
            raise ValueError("show file missing events list")
        return cls(schema_version=version, session=session, events=events)


def tick_ny_date(tick: TradeTick) -> str:
    dt = datetime.fromtimestamp(tick.ts_event_ns / 1_000_000_000, tz=NY)
    return dt.strftime("%Y-%m-%d")


def filter_ticks_by_day(ticks: list[TradeTick], day: str) -> list[TradeTick]:
    return [tick for tick in ticks if tick_ny_date(tick) == day]


def record_strategy_session(
    *,
    strategy: TickStrategy,
    ticks: list[TradeTick],
    cfg: PaperConfig,
    feed: str,
    interval: str,
    strategy_name: str,
    model_path: str | None,
    show_day: str | None = None,
    source_ticks_path: str | None = None,
) -> ShowRecording:
    if not ticks:
        raise ValueError("no ticks to record")

    seq = sorted(ticks, key=lambda t: (t.ts_event_ns, t.symbol))
    symbol = seq[0].symbol
    meta = DashboardMeta(
        feed=feed,
        symbol=symbol,
        interval=interval,
        strategy=strategy_name,
        model_path=model_path,
        initial_cash=cfg.initial_cash,
    )

    state = PaperState(cash=cfg.initial_cash, equity_peak=cfg.initial_cash)
    events: list[dict[str, object]] = []
    last_fill_count = 0

    for index, tick in enumerate(seq):
        state = apply_tick(
            strategy=strategy,
            tick=tick,
            index=index,
            n_ticks=len(seq),
            cfg=cfg,
            state=state,
        )
        fill = None
        if len(state.fills) > last_fill_count:
            fill = state.fills[-1]
            last_fill_count = len(state.fills)
        events.append(
            tick_snapshot(
                tick=tick,
                state=state,
                tick_index=index + 1,
                meta=meta,
                fill=fill,
            )
        )
        if state.killed:
            break

    first_day = tick_ny_date(seq[0])
    last_day = tick_ny_date(seq[-1])
    session_day = show_day or (first_day if first_day == last_day else f"{first_day}_to_{last_day}")

    session = {
        "mode": "show",
        "feed": feed,
        "symbol": symbol,
        "interval": interval,
        "strategy": strategy_name,
        "model_path": model_path,
        "initial_cash": cfg.initial_cash,
        "show_day": session_day,
        "bar_count": len(events),
        "fills_count": len(state.fills),
        "final_cash": round(state.cash, 2),
        "final_shares": state.shares,
        "source_ticks_path": source_ticks_path,
        "message": (
            f"Recorded show for {symbol} ({session_day}) — "
            f"{len(events)} decision bar(s), loops on the dashboard."
        ),
    }
    return ShowRecording(schema_version=SHOW_SCHEMA_VERSION, session=session, events=events)


def save_show(recording: ShowRecording, path: Path) -> Path:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(recording.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def load_show(path: Path) -> ShowRecording:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"show file must be a JSON object: {path}")
    return ShowRecording.from_dict(data)


def default_show_path(
    *,
    symbol: str,
    day: str,
    strategy: str,
    data_root: Path | None = None,
) -> Path:
    from crucibo.replay.bundle import default_runs_parent

    root = data_root or default_runs_parent()
    sym = symbol.upper()
    return root / "shows" / f"{sym}_{day}_{strategy}.json"