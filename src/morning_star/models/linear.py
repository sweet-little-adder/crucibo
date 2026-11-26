"""Linear / logistic model over standardised market features (linear_v1 artifact)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class LinearModel:
    mu: np.ndarray  # (d,) train-only mean
    sd: np.ndarray  # (d,) train-only std
    w: np.ndarray  # (d,)
    b: float
    link: str  # "sigmoid" (logistic regression) | "identity" (linear regression on forward return)
    feature_indices: tuple[int, ...]
    lookback: int
    forward_horizon: int
    threshold: float  # 0.5 for sigmoid, 0.0 for identity
    target_shares: int
    initial_cash: float

    def predict_score(self, features: np.ndarray) -> float:
        x = np.asarray(features, dtype=np.float64).reshape(-1)[list(self.feature_indices)]
        z = float(((x - self.mu) / self.sd) @ self.w + self.b)
        if self.link == "identity":
            return z
        z = max(-60.0, min(60.0, z))
        return 1.0 / (1.0 + math.exp(-z))

    def decide_shares(self, features: np.ndarray) -> int:
        return self.target_shares if self.predict_score(features) >= self.threshold else 0
