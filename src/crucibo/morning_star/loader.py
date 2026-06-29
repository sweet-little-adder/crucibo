"""Load morning-star artifact bundles without importing the morning-star package."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from crucibo.features import FEATURE_NAMES, FEATURE_SCHEMA_VERSION

CONTRACT_VERSION = 1
MODEL_TYPE_MLP_V1 = "mlp_v1"
MANIFEST_FILENAME = "manifest.json"
WEIGHTS_FILENAME = "weights.npz"


@dataclass(frozen=True)
class MorningStarModel:
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


def resolve_artifact_dir(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.is_dir():
        return resolved
    if resolved.is_file() and resolved.suffix == ".npz":
        return resolved.parent
    raise ValueError(f"morning-star artifact must be a directory or weights.npz: {path}")


def load_morning_star_model(path: Path) -> MorningStarModel:
    artifact_dir = resolve_artifact_dir(path)
    manifest_path = artifact_dir / MANIFEST_FILENAME
    weights_file = artifact_dir / WEIGHTS_FILENAME

    if not manifest_path.is_file():
        raise ValueError(f"missing {MANIFEST_FILENAME} in {artifact_dir}")
    if not weights_file.is_file():
        raise ValueError(f"missing {WEIGHTS_FILENAME} in {artifact_dir}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if int(manifest.get("contract_version", -1)) != CONTRACT_VERSION:
        raise ValueError(f"unsupported morning-star contract_version in {manifest_path}")
    if manifest.get("model_type") != MODEL_TYPE_MLP_V1:
        raise ValueError(f"unsupported morning-star model_type: {manifest.get('model_type')!r}")
    if int(manifest.get("feature_schema_version", -1)) != FEATURE_SCHEMA_VERSION:
        raise ValueError("unsupported morning-star feature_schema_version")
    names = manifest.get("feature_names")
    if tuple(names) != FEATURE_NAMES:
        raise ValueError("morning-star feature_names mismatch with crucibo feature schema v1")

    with np.load(weights_file, allow_pickle=False) as data:
        return MorningStarModel(
            w1=data["w1"],
            b1=data["b1"],
            w2=data["w2"],
            b2=data["b2"],
            lookback=int(manifest["lookback"]),
            forward_horizon=int(manifest["forward_horizon"]),
            threshold=float(manifest["threshold"]),
            target_shares=int(manifest["target_shares"]),
            initial_cash=float(manifest["initial_cash"]),
        )
