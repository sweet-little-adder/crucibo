"""Position reconciliation — intended local book vs broker snapshot."""

from __future__ import annotations

from dataclasses import dataclass

from crucibo.live.account import LocalAccount


@dataclass(frozen=True)
class BrokerSnapshot:
    """What the broker reports (cash + positions)."""

    cash: float | None
    positions: dict[str, int]  # symbol -> shares
    source: str = "broker"


@dataclass(frozen=True)
class ReconcileDiff:
    ok: bool
    cash_delta: float | None
    position_deltas: dict[str, int]
    reasons: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "cash_delta": self.cash_delta,
            "position_deltas": dict(self.position_deltas),
            "reasons": list(self.reasons),
        }


def reconcile_account(
    local: LocalAccount,
    broker: BrokerSnapshot,
    *,
    cash_tol: float = 0.02,
    shares_tol: int = 0,
) -> ReconcileDiff:
    """Compare local intended state to broker-reported state."""

    reasons: list[str] = []
    cash_delta: float | None = None
    if broker.cash is not None:
        cash_delta = local.cash - broker.cash
        if abs(cash_delta) > cash_tol:
            reasons.append(
                f"cash mismatch: local={local.cash:.4f} broker={broker.cash:.4f} "
                f"delta={cash_delta:.4f}"
            )

    broker_pos = {k.upper(): int(v) for k, v in broker.positions.items()}
    symbols = set(local.positions) | set(broker_pos)
    pos_deltas: dict[str, int] = {}
    for sym in sorted(symbols):
        local_q = local.position_shares(sym)
        broker_q = broker_pos.get(sym.upper(), 0)
        delta = local_q - broker_q
        if abs(delta) > shares_tol:
            pos_deltas[sym] = delta
            reasons.append(
                f"position {sym}: local={local_q} broker={broker_q} delta={delta}"
            )

    return ReconcileDiff(
        ok=len(reasons) == 0,
        cash_delta=cash_delta,
        position_deltas=pos_deltas,
        reasons=reasons,
    )
