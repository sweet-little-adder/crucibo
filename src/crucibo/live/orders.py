"""Order state machine — shared by dry-run and signed equity brokers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from crucibo.live.broker import OrderIntent, OrderResult, OrderSide, OrderStatus
from crucibo.models import utc_now_ns


class OrderPhase(StrEnum):
    """Lifecycle phases for an order under management."""

    NEW = "NEW"
    SUBMITTED = "SUBMITTED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELED = "CANCELED"


_TERMINAL = frozenset({OrderPhase.FILLED, OrderPhase.REJECTED, OrderPhase.CANCELED})

_ALLOWED: dict[OrderPhase, frozenset[OrderPhase]] = {
    OrderPhase.NEW: frozenset({OrderPhase.SUBMITTED, OrderPhase.REJECTED, OrderPhase.CANCELED}),
    OrderPhase.SUBMITTED: frozenset(
        {OrderPhase.PARTIAL, OrderPhase.FILLED, OrderPhase.REJECTED, OrderPhase.CANCELED}
    ),
    OrderPhase.PARTIAL: frozenset({OrderPhase.FILLED, OrderPhase.CANCELED, OrderPhase.REJECTED}),
    OrderPhase.FILLED: frozenset(),
    OrderPhase.REJECTED: frozenset(),
    OrderPhase.CANCELED: frozenset(),
}


@dataclass
class ManagedOrder:
    intent: OrderIntent
    phase: OrderPhase = OrderPhase.NEW
    broker_order_id: str | None = None
    filled_qty: int = 0
    avg_exec_price: float | None = None
    fee_cash: float = 0.0
    reason: str | None = None
    history: list[dict[str, object]] = field(default_factory=list)
    created_ns: int = field(default_factory=utc_now_ns)
    updated_ns: int = field(default_factory=utc_now_ns)

    @property
    def is_terminal(self) -> bool:
        return self.phase in _TERMINAL

    def transition(self, to: OrderPhase, *, reason: str | None = None) -> None:
        allowed = _ALLOWED[self.phase]
        if to not in allowed and to != self.phase:
            raise ValueError(f"illegal order transition {self.phase} → {to}")
        if to != self.phase:
            self.history.append(
                {
                    "from": self.phase.value,
                    "to": to.value,
                    "ts_ns": utc_now_ns(),
                    "reason": reason,
                }
            )
            self.phase = to
            self.updated_ns = utc_now_ns()
            if reason:
                self.reason = reason

    def apply_result(self, result: OrderResult) -> None:
        """Advance phase from a broker ack."""

        if self.phase == OrderPhase.NEW:
            self.transition(OrderPhase.SUBMITTED)

        if result.status == OrderStatus.REJECTED:
            self.transition(OrderPhase.REJECTED, reason=result.reason)
            return
        if result.status == OrderStatus.CANCELED:
            self.transition(OrderPhase.CANCELED, reason=result.reason)
            return
        if result.status == OrderStatus.FILLED:
            self.filled_qty = result.filled_qty
            self.avg_exec_price = result.exec_price
            self.fee_cash = result.fee_cash
            if result.filled_qty < self.intent.qty_shares:
                self.transition(OrderPhase.PARTIAL)
                if self.filled_qty >= self.intent.qty_shares:
                    self.transition(OrderPhase.FILLED)
            else:
                self.transition(OrderPhase.FILLED)
            return
        if result.status == OrderStatus.NEW:
            self.transition(OrderPhase.SUBMITTED)


@dataclass
class OrderBook:
    """In-memory order ledger keyed by client_order_id."""

    orders: dict[str, ManagedOrder] = field(default_factory=dict)

    def register(self, intent: OrderIntent) -> ManagedOrder:
        if intent.client_order_id in self.orders:
            raise ValueError(f"duplicate client_order_id: {intent.client_order_id}")
        mo = ManagedOrder(intent=intent)
        self.orders[intent.client_order_id] = mo
        return mo

    def apply(self, result: OrderResult) -> ManagedOrder:
        mo = self.orders.get(result.client_order_id)
        if mo is None:
            raise KeyError(f"unknown client_order_id: {result.client_order_id}")
        mo.apply_result(result)
        return mo

    def open_orders(self) -> list[ManagedOrder]:
        return [o for o in self.orders.values() if not o.is_terminal]

    def to_log(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for o in self.orders.values():
            rows.append(
                {
                    "client_order_id": o.intent.client_order_id,
                    "symbol": o.intent.symbol,
                    "side": (o.intent.side.value
                     if isinstance(o.intent.side, OrderSide)
                     else o.intent.side),
                    "qty_shares": o.intent.qty_shares,
                    "phase": o.phase.value,
                    "filled_qty": o.filled_qty,
                    "avg_exec_price": o.avg_exec_price,
                    "fee_cash": o.fee_cash,
                    "reason": o.reason,
                    "broker_order_id": o.broker_order_id,
                    "created_ns": o.created_ns,
                    "updated_ns": o.updated_ns,
                }
            )
        return rows
