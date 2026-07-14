"""Latency measurement for feed lag and decision path (HFT-shaped discipline)."""

from __future__ import annotations

from dataclasses import dataclass, field

from crucibo.models import utc_now_ns


@dataclass
class LatencyTracker:
    """Accumulate nanosecond samples; export summary stats for manifests."""

    feed_lag_ns: list[int] = field(default_factory=list)
    decision_ns: list[int] = field(default_factory=list)
    tick_to_order_ns: list[int] = field(default_factory=list)

    def record_feed_lag(self, *, ts_event_ns: int, ts_ingest_ns: int | None) -> None:
        if ts_ingest_ns is None or ts_ingest_ns < ts_event_ns:
            return
        self.feed_lag_ns.append(int(ts_ingest_ns - ts_event_ns))

    def record_decision(self, elapsed_ns: int) -> None:
        if elapsed_ns >= 0:
            self.decision_ns.append(int(elapsed_ns))

    def record_tick_to_order(self, elapsed_ns: int) -> None:
        if elapsed_ns >= 0:
            self.tick_to_order_ns.append(int(elapsed_ns))

    def span_start(self) -> int:
        return utc_now_ns()

    def span_end(self, start_ns: int) -> int:
        return max(0, utc_now_ns() - start_ns)

    def summary(self) -> dict[str, dict[str, float | int | None]]:
        return {
            "feed_lag": _stats(self.feed_lag_ns),
            "decision": _stats(self.decision_ns),
            "tick_to_order": _stats(self.tick_to_order_ns),
        }


def _stats(samples: list[int]) -> dict[str, float | int | None]:
    if not samples:
        return {"count": 0, "mean_ns": None, "p50_ns": None, "p99_ns": None, "max_ns": None}
    ordered = sorted(samples)
    n = len(ordered)
    return {
        "count": n,
        "mean_ns": float(sum(ordered) / n),
        "p50_ns": int(ordered[n // 2]),
        "p99_ns": int(ordered[min(n - 1, int(n * 0.99))]),
        "max_ns": int(ordered[-1]),
    }
