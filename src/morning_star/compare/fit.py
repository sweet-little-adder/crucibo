"""Fit comparison models on market features (ret_1, mean_ret, price_z) and convert to exportable models."""

from __future__ import annotations

import numpy as np

from morning_star.compare.harness import LB, H, Scaler, mlp_v2_proba, train_mlp_v2
from morning_star.contracts import MARKET_FEATURE_INDICES
from morning_star.models.baseline import BaselineMLP
from morning_star.models.linear import LinearModel
from morning_star.models.trees import TreeEnsemble, from_xgboost_booster

IDX = tuple(MARKET_FEATURE_INDICES)


def _common(target_shares: int, initial_cash: float, threshold: float) -> dict:
    return dict(
        feature_indices=IDX,
        lookback=LB,
        forward_horizon=H,
        threshold=threshold,
        target_shares=target_shares,
        initial_cash=initial_cash,
    )


def fit_logistic(X, y, *, C=1.0, target_shares=100, initial_cash=1e6) -> LinearModel:
    from sklearn.linear_model import LogisticRegression

    sc = Scaler().fit(X)
    m = LogisticRegression(C=C, max_iter=2000).fit(sc.tf(X), y)
    return LinearModel(
        mu=sc.mu,
        sd=sc.sd,
        w=m.coef_.reshape(-1),
        b=float(m.intercept_[0]),
        link="sigmoid",
        **_common(target_shares, initial_cash, 0.5),
    )


def fit_linear(X, fwd, *, target_shares=100, initial_cash=1e6) -> LinearModel:
    from sklearn.linear_model import LinearRegression

    sc = Scaler().fit(X)
    m = LinearRegression().fit(sc.tf(X), fwd)
    return LinearModel(
        mu=sc.mu,
        sd=sc.sd,
        w=np.asarray(m.coef_).reshape(-1),
        b=float(m.intercept_),
        link="identity",
        **_common(target_shares, initial_cash, 0.0),
    )


def fit_xgboost(X, y, params: dict, *, target_shares=100, initial_cash=1e6):
    """Returns (sklearn-API classifier, exportable TreeEnsemble)."""
    import xgboost as xgb

    clf = xgb.XGBClassifier(
        n_estimators=params["n_estimators"],
        max_depth=params["max_depth"],
        learning_rate=params["learning_rate"],
        subsample=params["subsample"],
        colsample_bytree=params["colsample_bytree"],
        min_child_weight=params["min_child_weight"],
        reg_lambda=params["reg_lambda"],
        random_state=params["seed"],
        n_jobs=4,
        verbosity=0,
    ).fit(X, y)
    ens = from_xgboost_booster(clf.get_booster(), **_common(target_shares, initial_cash, 0.5))
    return clf, ens


def fit_mlp_v2(X, y, params: dict):
    return train_mlp_v2(
        X,
        y,
        seed=params["seed"],
        hidden=params["hidden"],
        epochs=params["epochs"],
        lr=params["lr"],
        wd=params["weight_decay"],
    )


def mlp_v2_to_v1(sc, P, *, target_shares=100, initial_cash=1e6, threshold=0.5) -> BaselineMLP:
    """Fold train-only standardisation into layer 1 exactly; zero weights on position_norm/cash_norm.

    The result is a plain mlp_v1 artifact payload, loadable by existing v1 loaders.
    """
    w = P["w1"] / sc.sd[:, None]
    b = P["b1"] - (sc.mu / sc.sd) @ P["w1"]
    w5 = np.vstack([w, np.zeros((2, w.shape[1]))])
    return BaselineMLP(
        w1=w5,
        b1=b,
        w2=P["w2"],
        b2=P["b2"],
        lookback=LB,
        forward_horizon=H,
        threshold=threshold,
        target_shares=target_shares,
        initial_cash=initial_cash,
    )


__all__ = [
    "TreeEnsemble",
    "LinearModel",
    "fit_logistic",
    "fit_linear",
    "fit_xgboost",
    "fit_mlp_v2",
    "mlp_v2_to_v1",
    "mlp_v2_proba",
]
