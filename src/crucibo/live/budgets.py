"""Latency budgets — measure and optionally kill when exceeded."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LatencyBudget:
    """
    Soft/hard budgets in nanoseconds for HFT-shaped discipline.

    Exceeding ``warn_ns`` records a warning; exceeding ``kill_ns`` trips kill
    when ``enforce`` is True.
    """

    name: str
    warn_ns: int | None = None
    kill_ns: int | None = None
    enforce: bool = False
    warnings: list[dict[str, object]] = field(default_factory=list)
    violations: list[dict[str, object]] = field(default_factory=list)

    def observe(self, sample_ns: int, *, context: str = "") -> str | None:
        """Return kill reason if hard budget exceeded, else None."""

        if self.warn_ns is not None and sample_ns > self.warn_ns:
            self.warnings.append(
                {"name": self.name, "sample_ns": sample_ns, "context": context}
            )
        if self.kill_ns is not None and sample_ns > self.kill_ns:
            self.violations.append(
                {"name": self.name, "sample_ns": sample_ns, "context": context}
            )
            if self.enforce:
                return (
                    f"latency budget exceeded: {self.name} "
                    f"{sample_ns}ns > kill {self.kill_ns}ns"
                )
        return None

    def summary(self) -> dict[str, object]:
        return {
            "name": self.name,
            "warn_ns": self.warn_ns,
            "kill_ns": self.kill_ns,
            "enforce": self.enforce,
            "warning_count": len(self.warnings),
            "violation_count": len(self.violations),
        }


@dataclass
class BudgetBoard:
    """Named budgets for feed lag, decision, tick-to-order."""

    feed_lag: LatencyBudget = field(
        default_factory=lambda: LatencyBudget(
            name="feed_lag",
            warn_ns=5_000_000_000,  # 5s (AV free is delayed; warn only)
            kill_ns=None,
            enforce=False,
        )
    )
    decision: LatencyBudget = field(
        default_factory=lambda: LatencyBudget(
            name="decision",
            warn_ns=50_000_000,  # 50ms
            kill_ns=500_000_000,  # 500ms
            enforce=False,
        )
    )
    tick_to_order: LatencyBudget = field(
        default_factory=lambda: LatencyBudget(
            name="tick_to_order",
            warn_ns=100_000_000,  # 100ms
            kill_ns=1_000_000_000,  # 1s
            enforce=False,
        )
    )

    def summary(self) -> dict[str, object]:
        return {
            "feed_lag": self.feed_lag.summary(),
            "decision": self.decision.summary(),
            "tick_to_order": self.tick_to_order.summary(),
        }
