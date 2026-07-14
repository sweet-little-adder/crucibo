"""Live execution plane — US equities first; crypto remains optional elsewhere.

Import submodules directly when needed to keep import graphs light:
``from crucibo.live.runtime import LiveEquityRuntime``, etc.
"""

from crucibo.live.account import LocalAccount, Position
from crucibo.live.broker import DryRunBroker, OrderIntent, OrderResult, OrderSide, OrderStatus
from crucibo.live.budgets import BudgetBoard, LatencyBudget
from crucibo.live.clock import SessionClock
from crucibo.live.equity_broker import (
    AlpacaPaperBroker,
    DryRunEquityBroker,
    build_equity_broker,
)
from crucibo.live.latency import LatencyTracker
from crucibo.live.orders import ManagedOrder, OrderBook, OrderPhase
from crucibo.live.reconcile import BrokerSnapshot, ReconcileDiff, reconcile_account
from crucibo.live.risk import RiskLimits, RiskVerdict, check_pretrade, validate_live_safety
from crucibo.live.runtime import (
    LiveEquityConfig,
    LiveEquityRuntime,
    LiveEquityState,
    run_live_equities_session,
)

__all__ = [
    "AlpacaPaperBroker",
    "BrokerSnapshot",
    "BudgetBoard",
    "DryRunBroker",
    "DryRunEquityBroker",
    "LatencyBudget",
    "LatencyTracker",
    "LiveEquityConfig",
    "LiveEquityRuntime",
    "LiveEquityState",
    "LocalAccount",
    "ManagedOrder",
    "OrderBook",
    "OrderIntent",
    "OrderPhase",
    "OrderResult",
    "OrderSide",
    "OrderStatus",
    "Position",
    "ReconcileDiff",
    "RiskLimits",
    "RiskVerdict",
    "SessionClock",
    "build_equity_broker",
    "check_pretrade",
    "reconcile_account",
    "run_live_equities_session",
    "validate_live_safety",
]
