"""Evaluator for gradient-boosted trees (trees_v1 artifact). Pure numpy/python, no xgboost import.

Semantics follow XGBoost: go to the left child when float32(x[f]) < float32(split); NaN follows
the default direction. Margin = base_margin + sum(leaf values); score = sigmoid(margin).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TreeEnsemble:
    tree_offsets: np.ndarray  # (n_trees+1,) start index of each tree in the node arrays
    left: np.ndarray  # absolute node index of left child, -1 for leaf
    right: np.ndarray
    feature: np.ndarray  # feature index within the selected market features
    split: np.ndarray  # float32-valued thresholds stored as float64
    value: np.ndarray  # leaf value (float64), unused for internal nodes
    default_left: np.ndarray  # bool
    base_margin: float
    feature_indices: tuple[int, ...]
    lookback: int
    forward_horizon: int
    threshold: float
    target_shares: int
    initial_cash: float

    @property
    def n_trees(self) -> int:
        return int(len(self.tree_offsets) - 1)

    def predict_margin(self, features: np.ndarray) -> float:
        x = np.asarray(features, dtype=np.float64).reshape(-1)[list(self.feature_indices)]
        x32 = x.astype(np.float32)
        total = self.base_margin
        for t in range(self.n_trees):
            n = int(self.tree_offsets[t])
            while self.left[n] >= 0:
                v = x32[self.feature[n]]
                if math.isnan(float(v)):
                    n = int(self.left[n] if self.default_left[n] else self.right[n])
                elif float(v) < float(np.float32(self.split[n])):
                    n = int(self.left[n])
                else:
                    n = int(self.right[n])
            total += float(self.value[n])
        return total

    def predict_score(self, features: np.ndarray) -> float:
        m = max(-60.0, min(60.0, self.predict_margin(features)))
        return 1.0 / (1.0 + math.exp(-m))

    def decide_shares(self, features: np.ndarray) -> int:
        return self.target_shares if self.predict_score(features) >= self.threshold else 0


def from_xgboost_booster(
    booster,
    *,
    feature_indices: tuple[int, ...],
    lookback: int,
    forward_horizon: int,
    threshold: float,
    target_shares: int,
    initial_cash: float,
) -> TreeEnsemble:
    """Convert a trained binary:logistic xgboost Booster (gbtree) into a TreeEnsemble."""
    import json

    cfg = json.loads(booster.save_config())
    objective = cfg["learner"]["objective"]["name"]
    if objective != "binary:logistic":
        raise ValueError(f"only binary:logistic is supported, got {objective!r}")
    raw_base = str(cfg["learner"]["learner_model_param"]["base_score"]).strip("[]")
    base_score = float(raw_base)
    base_margin = math.log(base_score / (1.0 - base_score))

    left: list[int] = []
    right: list[int] = []
    feat: list[int] = []
    split: list[float] = []
    value: list[float] = []
    dleft: list[bool] = []
    offsets = [0]
    for dump in booster.get_dump(dump_format="json"):
        root = json.loads(dump)
        nodes: dict[int, dict] = {}

        stack = [root]
        while stack:
            node = stack.pop()
            nodes[int(node["nodeid"])] = node
            stack.extend(node.get("children", []))
        base = len(left)
        order = sorted(nodes)
        index = {nid: base + i for i, nid in enumerate(order)}
        for nid in order:
            nd = nodes[nid]
            if "leaf" in nd:
                left.append(-1)
                right.append(-1)
                feat.append(0)
                split.append(0.0)
                value.append(float(nd["leaf"]))
                dleft.append(True)
            else:
                left.append(index[int(nd["yes"])])
                right.append(index[int(nd["no"])])
                feat.append(int(str(nd["split"]).lstrip("f")))
                split.append(float(np.float32(nd["split_condition"])))
                value.append(0.0)
                dleft.append(int(nd["missing"]) == int(nd["yes"]))
        offsets.append(len(left))
    return TreeEnsemble(
        tree_offsets=np.array(offsets, dtype=np.int64),
        left=np.array(left, dtype=np.int64),
        right=np.array(right, dtype=np.int64),
        feature=np.array(feat, dtype=np.int64),
        split=np.array(split, dtype=np.float64),
        value=np.array(value, dtype=np.float64),
        default_left=np.array(dleft, dtype=bool),
        base_margin=base_margin,
        feature_indices=tuple(feature_indices),
        lookback=lookback,
        forward_horizon=forward_horizon,
        threshold=threshold,
        target_shares=target_shares,
        initial_cash=initial_cash,
    )
