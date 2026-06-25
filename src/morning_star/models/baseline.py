"""Baseline numpy MLP — v1 export format."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BaselineMLP:
    w1: np.ndarray
    b1: np.ndarray
    w2: np.ndarray
    b2: np.ndarray
    lookback: int
    forward_horizon: int
    threshold: float
    target_shares: int
    initial_cash: float

    @property
    def hidden_dim(self) -> int:
        return int(self.w1.shape[1])

    def predict_proba(self, features: np.ndarray) -> float:
        x = np.asarray(features, dtype=np.float64).reshape(1, -1)
        h = np.tanh(x @ self.w1 + self.b1)
        logit = float(np.clip((h @ self.w2 + self.b2).item(), -60.0, 60.0))
        return 1.0 / (1.0 + math.exp(-logit))

    def decide_shares(self, features: np.ndarray) -> int:
        prob = self.predict_proba(features)
        return self.target_shares if prob >= self.threshold else 0
