"""TickStrategy backed by an aapl_mlp_v1 artifact bundle."""

from __future__ import annotations

from pathlib import Path

from crucibo.aapl_mlp_v1.loader import AaplMlpV1Model, load_aapl_mlp_v1_model
from crucibo.features import FeatureState
from crucibo.models import TradeTick


class AaplMlpV1Strategy:
    def __init__(self, model: AaplMlpV1Model) -> None:
        self._model = model
        self._state = FeatureState(
            lookback=model.lookback,
            initial_cash=model.initial_cash,
            max_position=model.target_shares,
        )

    @classmethod
    def from_artifact(cls, path: Path) -> AaplMlpV1Strategy:
        return cls(load_aapl_mlp_v1_model(path))

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