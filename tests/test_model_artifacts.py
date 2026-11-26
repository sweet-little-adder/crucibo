"""Export parity for linear_v1, trees_v1, mlp_v2 as mlp_v1; old loaders reject new types."""

from __future__ import annotations

import json

import numpy as np
import pytest

pytest.importorskip("sklearn")
xgb = pytest.importorskip("xgboost")

from morning_star.compare import fit as F  # noqa: E402
from morning_star.compare.harness import features, labels, mlp_v2_proba  # noqa: E402
from morning_star.export.artifact import load_baseline_mlp, save_artifact  # noqa: E402
from morning_star.export.artifact_models import (  # noqa: E402
    load_model,
    save_linear_artifact,
    save_trees_artifact,
)

rng = np.random.default_rng(1)
C = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, 900)))
X = features(C)
FWD = labels(C)
OK = ~np.isnan(X[:, 0]) & ~np.isnan(FWD)
TR = np.where(OK)[0][:600]
TE = np.where(OK)[0][600:]
Y = (FWD > 0).astype(float)
XGB_PARAMS = dict(
    n_estimators=60,
    max_depth=3,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=10,
    reg_lambda=5,
    seed=42,
)
FULL = np.hstack([X, np.zeros((len(X), 1)), np.ones((len(X), 1))])  # 5-dim runtime vector


def test_logistic_export_parity(tmp_path):
    m = F.fit_logistic(X[TR], Y[TR])
    save_linear_artifact(m, tmp_path / "a")
    m2 = load_model(tmp_path / "a")
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    ref = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)).fit(X[TR], Y[TR])
    got = np.array([m2.predict_score(FULL[i]) for i in TE])
    np.testing.assert_allclose(got, ref.predict_proba(X[TE])[:, 1], atol=1e-9)


def test_linear_regression_export_parity(tmp_path):
    m = F.fit_linear(X[TR], FWD[TR])
    save_linear_artifact(m, tmp_path / "a")
    m2 = load_model(tmp_path / "a")
    from sklearn.linear_model import LinearRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    ref = make_pipeline(StandardScaler(), LinearRegression()).fit(X[TR], FWD[TR])
    got = np.array([m2.predict_score(FULL[i]) for i in TE])
    np.testing.assert_allclose(got, ref.predict(X[TE]), atol=1e-9)
    assert m2.threshold == 0.0 and m2.link == "identity"


def test_xgboost_tree_export_parity(tmp_path):
    clf, ens = F.fit_xgboost(X[TR], Y[TR], XGB_PARAMS)
    save_trees_artifact(ens, tmp_path / "a")
    m2 = load_model(tmp_path / "a")
    got = np.array([m2.predict_score(FULL[i]) for i in TE])
    np.testing.assert_allclose(got, clf.predict_proba(X[TE])[:, 1], atol=1e-5)
    # decisions agree except possibly at float-noise ties
    agree = ((got >= 0.5) == (clf.predict_proba(X[TE])[:, 1] >= 0.5)).mean()
    assert agree > 0.995


def test_mlp_v2_folds_into_v1_artifact(tmp_path):
    p = dict(seed=42, hidden=8, epochs=100, lr=0.01, weight_decay=1e-3)
    sc, P = F.fit_mlp_v2(X[TR], Y[TR], p)
    m = F.mlp_v2_to_v1(sc, P, target_shares=10)
    save_artifact(m, tmp_path / "a", ticks_path=tmp_path / "x.parquet", tick_count=1, symbol="S")
    m2 = load_model(tmp_path / "a")  # same loader path as legacy mlp_v1
    got = np.array([m2.predict_proba(FULL[i]) for i in TE])
    np.testing.assert_allclose(got, mlp_v2_proba(sc, P, X[TE]), atol=1e-9)
    assert np.all(m2.w1[3:] == 0)  # position_norm, cash_norm cannot influence decisions
    # state feedback cannot change the output
    other = FULL[TE[0]].copy()
    other[3], other[4] = 1.0, 0.2
    assert abs(m2.predict_proba(other) - m2.predict_proba(FULL[TE[0]])) < 1e-12


def test_old_mlp_loader_rejects_new_types_loudly(tmp_path):
    m = F.fit_logistic(X[TR], Y[TR])
    save_linear_artifact(m, tmp_path / "a")
    with pytest.raises(ValueError, match="unsupported model_type"):
        load_baseline_mlp(tmp_path / "a")


def test_manifest_declares_market_features_only(tmp_path):
    m = F.fit_logistic(X[TR], Y[TR])
    save_linear_artifact(m, tmp_path / "a", extra_manifest={"trained_on": "synthetic"})
    mf = json.loads((tmp_path / "a" / "manifest.json").read_text())
    assert mf["feature_indices"] == [0, 1, 2] and mf["contract_version"] == 1
    assert mf["model_type"] == "linear_v1" and mf["feature_names"][3] == "position_norm"
