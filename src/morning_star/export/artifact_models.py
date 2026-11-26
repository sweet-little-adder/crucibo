"""Export / load linear_v1 and trees_v1 artifacts (contract_version 1, additive model types).

The existing mlp_v1 path in artifact.py is untouched. Layout matches the v1 bundle:
manifest.json + weights.npz. Crucibo loads these with its own loader (no morning-star import).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from morning_star.contracts import (
    ACTION_TARGET_SHARES,
    CONTRACT_VERSION,
    MANIFEST_FILENAME,
    MODEL_TYPE_LINEAR_V1,
    MODEL_TYPE_MLP_V1,
    MODEL_TYPE_TREES_V1,
    PRODUCER,
    WEIGHTS_FILENAME,
)
from morning_star.export.artifact import load_baseline_mlp, resolve_artifact_dir
from morning_star.features.schema import FEATURE_NAMES, FEATURE_SCHEMA_VERSION
from morning_star.models.linear import LinearModel
from morning_star.models.trees import TreeEnsemble


def _manifest(model, model_type: str, extra: dict[str, Any] | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "producer": PRODUCER,
        "model_type": model_type,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": list(FEATURE_NAMES),
        "feature_indices": list(model.feature_indices),
        "lookback": model.lookback,
        "forward_horizon": model.forward_horizon,
        "threshold": model.threshold,
        "target_shares": model.target_shares,
        "initial_cash": model.initial_cash,
        "action_type": ACTION_TARGET_SHARES,
    }
    if extra:
        payload.update(extra)
    return payload


def save_linear_artifact(
    model: LinearModel, out_dir: Path, *, extra_manifest: dict[str, Any] | None = None
) -> Path:
    d = out_dir.resolve()
    d.mkdir(parents=True, exist_ok=True)
    payload = _manifest(model, MODEL_TYPE_LINEAR_V1, extra_manifest)
    payload["link"] = model.link
    (d / MANIFEST_FILENAME).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    np.savez(d / WEIGHTS_FILENAME, mu=model.mu, sd=model.sd, w=model.w, b=np.array(model.b))
    return d


def save_trees_artifact(
    model: TreeEnsemble, out_dir: Path, *, extra_manifest: dict[str, Any] | None = None
) -> Path:
    d = out_dir.resolve()
    d.mkdir(parents=True, exist_ok=True)
    payload = _manifest(model, MODEL_TYPE_TREES_V1, extra_manifest)
    payload["link"] = "sigmoid"
    payload["n_trees"] = model.n_trees
    (d / MANIFEST_FILENAME).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    np.savez(
        d / WEIGHTS_FILENAME,
        tree_offsets=model.tree_offsets,
        left=model.left,
        right=model.right,
        feature=model.feature,
        split=model.split,
        value=model.value,
        default_left=model.default_left,
        base_margin=np.array(model.base_margin),
    )
    return d


def load_model(path: Path):
    """Load any supported artifact (mlp_v1, linear_v1, trees_v1) into its model object."""
    d = resolve_artifact_dir(path)
    manifest = json.loads((d / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    if int(manifest.get("contract_version", -1)) != CONTRACT_VERSION:
        raise ValueError("unsupported contract_version")
    if int(manifest.get("feature_schema_version", -1)) != FEATURE_SCHEMA_VERSION:
        raise ValueError("unsupported feature_schema_version")
    mtype = manifest.get("model_type")
    if mtype == MODEL_TYPE_MLP_V1:
        return load_baseline_mlp(d)
    common = dict(
        feature_indices=tuple(int(i) for i in manifest["feature_indices"]),
        lookback=int(manifest["lookback"]),
        forward_horizon=int(manifest["forward_horizon"]),
        threshold=float(manifest["threshold"]),
        target_shares=int(manifest["target_shares"]),
        initial_cash=float(manifest["initial_cash"]),
    )
    with np.load(d / WEIGHTS_FILENAME, allow_pickle=False) as z:
        if mtype == MODEL_TYPE_LINEAR_V1:
            return LinearModel(
                mu=z["mu"],
                sd=z["sd"],
                w=z["w"],
                b=float(z["b"]),
                link=str(manifest["link"]),
                **common,
            )
        if mtype == MODEL_TYPE_TREES_V1:
            return TreeEnsemble(
                tree_offsets=z["tree_offsets"],
                left=z["left"],
                right=z["right"],
                feature=z["feature"],
                split=z["split"],
                value=z["value"],
                default_left=z["default_left"],
                base_margin=float(z["base_margin"]),
                **common,
            )
    raise ValueError(f"unsupported model_type {mtype!r}")
