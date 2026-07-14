"""Named strategy factory for CLI and programmatic backtests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from crucibo.strategies.base import Strategy
from crucibo.strategies.ma_crossover import MaCrossoverStrategy
from crucibo.strategies.mean_reversion import MeanReversionStrategy

StrategyFactory = Callable[..., Strategy]

_REGISTRY: dict[str, StrategyFactory] = {
    "ma_crossover": lambda **kw: MaCrossoverStrategy(
        fast=int(kw.get("fast", 12)),
        slow=int(kw.get("slow", 26)),
        target_shares=int(kw.get("target_shares", 100)),
    ),
    "mean_reversion": lambda **kw: MeanReversionStrategy(
        lookback=int(kw.get("lookback", 20)),
        entry_z=float(kw.get("entry_z", 1.0)),
        target_shares=int(kw.get("target_shares", 100)),
    ),
}


def list_strategies() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def resolve_strategy(name: str, **kwargs: Any) -> Strategy:
    key = name.strip().lower().replace("-", "_")
    factory = _REGISTRY.get(key)
    if factory is None:
        raise ValueError(f"unknown strategy {name!r} (try {' | '.join(list_strategies())})")
    return factory(**kwargs)