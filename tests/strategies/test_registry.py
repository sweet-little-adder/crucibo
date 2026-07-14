"""Strategy registry resolution."""

from __future__ import annotations

import pytest

from crucibo.strategies.ma_crossover import MaCrossoverStrategy
from crucibo.strategies.mean_reversion import MeanReversionStrategy
from crucibo.strategies.registry import list_strategies, resolve_strategy


def test_list_strategies() -> None:
    names = list_strategies()
    assert "ma_crossover" in names
    assert "mean_reversion" in names


def test_resolve_ma_crossover() -> None:
    strat = resolve_strategy("ma_crossover", fast=5, slow=10, target_shares=25)
    assert isinstance(strat, MaCrossoverStrategy)


def test_resolve_mean_reversion_alias() -> None:
    strat = resolve_strategy("mean-reversion", lookback=10, entry_z=1.5)
    assert isinstance(strat, MeanReversionStrategy)


def test_resolve_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown strategy"):
        resolve_strategy("not_a_strategy")