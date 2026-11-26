"""Write and read artifact bundles for crucibo replay."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from morning_star.contracts import (
    ACTION_TARGET_SHARES,
    CONTRACT_VERSION,
    MANIFEST_FILENAME,
    MODEL_TYPE_MLP_V1,
    PRODUCER,
    WEIGHTS_FILENAME,
)
from morning_star.features.schema import FEATURE_DIM, FEATURE_NAMES, FEATURE_SCHEMA_VERSION
from morning_star.models.baseline import BaselineMLP


@dataclass(frozen=True)
class ArtifactManifest:
    contract_version: int
    producer: str
    model_type: str
    feature_schema_version: int
    feature_names: tuple[str, ...]
    lookback: int
    forward_horizon: int
    threshold: float
    target_shares: int
    initial_cash: float
    hidden_dim: int
    action_type: str
    training_ticks_path: str
    training_tick_count: int
    training_symbol: str | None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["feature_names"] = list(self.feature_names)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArtifactManifest:
        names = data.get("feature_names")
        if not isinstance(names, list):
            raise ValueError("manifest missing feature_names list")
        return cls(
            contract_version=int(data["contract_version"]),
            producer=str(data["producer"]),
            model_type=str(data["model_type"]),
            feature_schema_version=int(data["feature_schema_version"]),
            feature_names=tuple(str(n) for n in names),
            lookback=int(data["lookback"]),
            forward_horizon=int(data["forward_horizon"]),
            threshold=float(data["threshold"]),
            target_shares=int(data["target_shares"]),
            initial_cash=float(data["initial_cash"]),
            hidden_dim=int(data["hidden_dim"]),
            action_type=str(data["action_type"]),
            training_ticks_path=str(data["training_ticks_path"]),
            training_tick_count=int(data["training_tick_count"]),
            training_symbol=data.get("training_symbol"),
        )


def resolve_artifact_dir(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.is_dir():
        return resolved
    if resolved.is_file() and resolved.suffix == ".npz":
        return resolved.parent
    raise ValueError(f"artifact path must be a directory or weights.npz file: {path}")


def manifest_path(artifact_dir: Path) -> Path:
    return artifact_dir / MANIFEST_FILENAME


def weights_path(artifact_dir: Path) -> Path:
    return artifact_dir / WEIGHTS_FILENAME


def save_artifact(
    model: BaselineMLP,
    out_dir: Path,
    *,
    ticks_path: Path,
    tick_count: int,
    symbol: str | None,
    extra_manifest: dict[str, Any] | None = None,
) -> Path:
    artifact_dir = out_dir.resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)

    manifest = ArtifactManifest(
        contract_version=CONTRACT_VERSION,
        producer=PRODUCER,
        model_type=MODEL_TYPE_MLP_V1,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        feature_names=FEATURE_NAMES,
        lookback=model.lookback,
        forward_horizon=model.forward_horizon,
        threshold=model.threshold,
        target_shares=model.target_shares,
        initial_cash=model.initial_cash,
        hidden_dim=model.hidden_dim,
        action_type=ACTION_TARGET_SHARES,
        training_ticks_path=str(ticks_path.resolve()),
        training_tick_count=tick_count,
        training_symbol=symbol,
    )
    payload = manifest.to_dict()
    if extra_manifest:
        payload.update(extra_manifest)
    manifest_path(artifact_dir).write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    np.savez(
        weights_path(artifact_dir),
        w1=model.w1,
        b1=model.b1,
        w2=model.w2,
        b2=model.b2,
        feature_dim=np.array(FEATURE_DIM),
    )
    return artifact_dir


def load_manifest(path: Path) -> ArtifactManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    return ArtifactManifest.from_dict(data)


def load_baseline_mlp(artifact_dir: Path) -> BaselineMLP:
    resolved = resolve_artifact_dir(artifact_dir)
    raw_type = json.loads(manifest_path(resolved).read_text(encoding="utf-8")).get("model_type")
    if raw_type != MODEL_TYPE_MLP_V1:
        raise ValueError(f"unsupported model_type {raw_type!r}")
    manifest = load_manifest(manifest_path(resolved))
    if manifest.contract_version != CONTRACT_VERSION:
        raise ValueError(
            f"unsupported contract_version {manifest.contract_version} "
            f"(expected {CONTRACT_VERSION})"
        )
    if manifest.model_type != MODEL_TYPE_MLP_V1:
        raise ValueError(f"unsupported model_type {manifest.model_type!r}")
    if manifest.feature_schema_version != FEATURE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported feature_schema_version {manifest.feature_schema_version}"
        )
    if tuple(manifest.feature_names) != FEATURE_NAMES:
        raise ValueError("feature_names mismatch with morning-star schema v1")

    with np.load(weights_path(resolved), allow_pickle=False) as data:
        return BaselineMLP(
            w1=data["w1"],
            b1=data["b1"],
            w2=data["w2"],
            b2=data["b2"],
            lookback=manifest.lookback,
            forward_horizon=manifest.forward_horizon,
            threshold=manifest.threshold,
            target_shares=manifest.target_shares,
            initial_cash=manifest.initial_cash,
        )
