"""Simple tick-by-tick deterministic replay (education / scaffolding)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from crucibo.features import FeatureState
from crucibo.mlp import MLPModel, load_mlp
from crucibo.models import TradeTick


class TickStrategy(Protocol):
    """Targets **absolute** position in whole shares."""

    def desired_shares(
        self,
        *,
        tick: TradeTick,
        index: int,
        n_ticks: int,
        position: int,
        cash: float,
    ) -> int: ...


class AlwaysFlat:
    def desired_shares(
        self,
        *,
        tick: TradeTick,
        index: int,
        n_ticks: int,
        position: int,
        cash: float,
    ) -> int:
        return 0


class BuyAndHold:
    """Maintain a constant target long position after the first observation."""

    def __init__(self, target_shares: int) -> None:
        if target_shares < 0:
            raise ValueError("target_shares must be >= 0 for this toy sim")
        self._target_shares = target_shares

    def desired_shares(
        self,
        *,
        tick: TradeTick,
        index: int,
        n_ticks: int,
        position: int,
        cash: float,
    ) -> int:
        del tick, cash
        del index, n_ticks
        return self._target_shares


class NeuralStrategy:
    """Strategy backed by a trained numpy MLP checkpoint."""

    def __init__(self, model: MLPModel) -> None:
        self._model = model
        self._state = FeatureState(
            lookback=model.lookback,
            initial_cash=model.initial_cash,
            max_position=model.target_shares,
        )

    @classmethod
    def from_checkpoint(cls, path: Path) -> NeuralStrategy:
        return cls(load_mlp(path))

    def desired_shares(
        self,
        *,
        tick: TradeTick,
        index: int,
        n_ticks: int,
        position: int,
        cash: float,
    ) -> int:
        del index, n_ticks
        vec = self._state.update(tick, position=position, cash=cash)
        if vec is None:
            return 0
        return self._model.decide_shares(vec)


def resolve_strategy(
    name: str,
    *,
    target_shares: int = 100,
    model_path: Path | None = None,
) -> TickStrategy:
    key = name.strip().lower().replace("-", "_")
    if key in {"flat", "always_flat"}:
        return AlwaysFlat()
    if key in {"buy_hold", "buyandhold"}:
        return BuyAndHold(target_shares)
    if key in {"neural", "mlp", "model"}:
        if model_path is None:
            raise ValueError("neural strategy requires --model PATH to a trained .npz checkpoint")
        return NeuralStrategy.from_checkpoint(model_path)
    raise ValueError(f"unknown strategy: {name!r} (try flat | buy_hold | neural)")
