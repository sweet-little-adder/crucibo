"""TickStrategy backed by a morning-star artifact bundle."""

from __future__ import annotations

from pathlib import Path

from crucibo.features import FeatureState
from crucibo.models import TradeTick
from crucibo.morning_star.loader import MorningStarModel, load_morning_star_model


class MorningStarStrategy:
    def __init__(self, model: MorningStarModel) -> None:
        self._model = model
        self._state = FeatureState(
            lookback=model.lookback,
            initial_cash=model.initial_cash,
            max_position=model.target_shares,
        )

    @classmethod
    def from_artifact(cls, path: Path) -> MorningStarStrategy:
        return cls(load_morning_star_model(path))

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
