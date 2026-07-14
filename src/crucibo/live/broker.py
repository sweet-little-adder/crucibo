"""Broker abstractions — dry-run now; signed live REST later."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from crucibo.models import utc_now_ns


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(StrEnum):
    NEW = "NEW"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELED = "CANCELED"


@dataclass(frozen=True)
class OrderIntent:
    """What the strategy/runtime wants the broker to do."""

    client_order_id: str
    symbol: str
    side: OrderSide
    qty_shares: int
    mark_price: float
    ts_event_ns: int
    mode: str = "paper"  # paper | live_dry_run | live


@dataclass
class OrderResult:
    client_order_id: str
    status: OrderStatus
    filled_qty: int = 0
    exec_price: float | None = None
    fee_cash: float = 0.0
    reason: str | None = None
    ts_ack_ns: int = field(default_factory=utc_now_ns)


class Broker(Protocol):
    def submit(self, intent: OrderIntent) -> OrderResult: ...


@dataclass
class DryRunBroker:
    """
    Live-path dry-run: same virtual fill economics as paper, but records order
    lifecycle as if a broker were involved. Never sends network orders.
    """

    slip_bps: float = 2.0
    fee_per_share: float = 0.0
    order_log: list[dict[str, object]] = field(default_factory=list)

    def submit(self, intent: OrderIntent) -> OrderResult:
        if intent.qty_shares <= 0:
            result = OrderResult(
                client_order_id=intent.client_order_id,
                status=OrderStatus.REJECTED,
                reason="qty must be positive",
            )
            self._log(intent, result)
            return result

        slip_m = self.slip_bps / 10_000.0
        if intent.side == OrderSide.BUY:
            exec_px = intent.mark_price * (1.0 + slip_m)
        else:
            exec_px = intent.mark_price * (1.0 - slip_m)
        fee = intent.qty_shares * self.fee_per_share
        result = OrderResult(
            client_order_id=intent.client_order_id,
            status=OrderStatus.FILLED,
            filled_qty=intent.qty_shares,
            exec_price=exec_px,
            fee_cash=fee,
        )
        self._log(intent, result)
        return result

    def _log(self, intent: OrderIntent, result: OrderResult) -> None:
        self.order_log.append(
            {
                "client_order_id": intent.client_order_id,
                "symbol": intent.symbol,
                "side": intent.side.value,
                "qty_shares": intent.qty_shares,
                "mark_price": intent.mark_price,
                "ts_event_ns": intent.ts_event_ns,
                "mode": intent.mode,
                "status": result.status.value,
                "filled_qty": result.filled_qty,
                "exec_price": result.exec_price,
                "fee_cash": result.fee_cash,
                "reason": result.reason,
                "ts_ack_ns": result.ts_ack_ns,
            }
        )
