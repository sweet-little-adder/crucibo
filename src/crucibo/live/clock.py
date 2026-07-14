"""US equities session clock (RTH) — event-time honesty for stocks-first path."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")

# Regular trading hours (no early close handling — v1)
_RTH_OPEN = time(9, 30)
_RTH_CLOSE = time(16, 0)


@dataclass(frozen=True)
class SessionClock:
    """Filter / label US equity event timestamps against RTH."""

    include_extended: bool = False

    def event_dt_ny(self, ts_event_ns: int) -> datetime:
        return datetime.fromtimestamp(ts_event_ns / 1_000_000_000, tz=UTC).astimezone(_NY)

    def is_rth(self, ts_event_ns: int) -> bool:
        dt = self.event_dt_ny(ts_event_ns)
        if dt.weekday() >= 5:
            return False
        t = dt.time()
        if self.include_extended:
            # 4:00–20:00 ET rough extended window
            return time(4, 0) <= t <= time(20, 0)
        return _RTH_OPEN <= t < _RTH_CLOSE

    def should_trade(self, ts_event_ns: int, *, rth_only: bool) -> bool:
        if not rth_only:
            return True
        return self.is_rth(ts_event_ns)

    def label(self, ts_event_ns: int) -> str:
        return "RTH" if self.is_rth(ts_event_ns) else "OUTSIDE_RTH"
