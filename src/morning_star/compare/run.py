"""Run the predeclared walk-forward comparison from a frozen config and write results + provenance."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from morning_star.compare import fit as F
from morning_star.compare.harness import (
    LB,
    H,
    auc,
    boot_auc,
    boot_mean,
    features,
    fold_slices,
    labels,
    load,
    simulate,
    stats,
)

MODELS = ["buy&hold", "logistic", "linear_reg", "xgboost", "mlp_v2", "mlp_shipped_v1"]


def _shipped_proba(df, last_label_bar, X3):
    from morning_star.ticks import Tick
    from morning_star.train.loop import train_baseline_mlp

    ticks = [
        Tick(ts_event_ns=i + 1, symbol="S", price=float(p), size=1)
        for i, p in enumerate(df.c.values[: last_label_bar + 1])
    ]
    m = train_baseline_mlp(
        ticks,
        lookback=LB,
        forward_horizon=H,
        hidden_dim=8,
        epochs=80,
        learning_rate=0.05,
        seed=42,
        threshold=0.5,
        target_shares=1,
        initial_cash=1e6,
    )
    X5 = np.hstack([X3, np.zeros((len(X3), 1)), np.ones((len(X3), 1))])
    z = np.tanh(X5 @ m.w1 + m.b1) @ m.w2 + m.b2
    return (1 / (1 + np.exp(-np.clip(z, -60, 60)))).reshape(-1)


def fit_fold_models(df, X, y, fwd, tr, cfg):
    mc = cfg["models"]
    Xtr = X[tr]
    clf, ens = F.fit_xgboost(Xtr, y[tr], mc["xgboost"])
    sc, P = F.fit_mlp_v2(Xtr, y[tr], mc["mlp_v2"])
    return dict(
        logistic=F.fit_logistic(Xtr, y[tr], C=mc["logistic"]["C"]),
        linear_reg=F.fit_linear(Xtr, fwd[tr]),
        xgb_clf=clf,
        xgb_ens=ens,
        mlp=(sc, P),
    )


def _score_all(models, Xte):
    from morning_star.compare.harness import mlp_v2_proba

    def lin(m):  # vectorised LinearModel score
        z = ((Xte - m.mu) / m.sd) @ m.w + m.b
        return z if m.link == "identity" else 1 / (1 + np.exp(-np.clip(z, -60, 60)))

    return dict(
        logistic=lin(models["logistic"]),
        linear_reg=lin(models["linear_reg"]),
        xgboost=models["xgb_clf"].predict_proba(Xte)[:, 1],
        mlp_v2=mlp_v2_proba(*models["mlp"], Xte),
    )


def run_symbol(sym, cfg, data_dir):
    df = load(sym, data_dir)
    o, c = df.o.values, df.c.values
    X = features(c)
    fwd = labels(c)
    valid = ~np.isnan(X[:, 0]) & ~np.isnan(fwd)
    y = (fwd > 0).astype(float)
    scores = {m: np.full(len(df), np.nan) for m in MODELS}
    folds = fold_slices(
        df.date.values, cfg["folds"]["test_years"], cfg["folds"]["min_train_rows"], valid
    )
    for _yr, tr, te in folds:
        models = fit_fold_models(df, X, y, fwd, tr, cfg)
        scores["buy&hold"][te] = 1
        for k, v in _score_all(models, X[te]).items():
            scores[k][te] = v
        scores["mlp_shipped_v1"][te] = _shipped_proba(df, tr[-1] + H, X[te])
    te_all = np.concatenate([f[2] for f in folds])
    yr_list = [f[0] for f in folds]
    dec = {
        m: (scores[m][te_all] > 0).astype(float)
        if m == "linear_reg"
        else (scores[m][te_all] >= 0.5).astype(float)
        for m in MODELS
    }
    out = dict(
        symbol=sym,
        test_first=df.date[te_all[0]],
        test_last=df.date[te_all[-1]],
        n_test=len(te_all),
        years=yr_list,
        models={},
    )
    lab_ok = ~np.isnan(fwd[te_all])
    costs = [0, 6, 12]
    bh = {k: simulate(o, c, dec["buy&hold"], te_all, k)[0] for k in costs}
    for m in MODELS:
        d = {}
        if m != "buy&hold":
            s = scores[m][te_all][lab_ok]
            yy = y[te_all][lab_ok]
            d["auc"] = auc(s, yy)
            d["auc_ci95"] = boot_auc(s, yy)
            d["accuracy"] = float((dec[m][lab_ok] == yy).mean())
        d["base_rate_up"] = float(y[te_all][lab_ok].mean())
        d["costs"] = {}
        for k in costs:
            r, t, p = simulate(o, c, dec[m], te_all, k)
            st = stats(r, t, p)
            ex = r - bh[k]
            st["mean_daily_excess_vs_bh_bps"] = float(ex.mean() * 1e4)
            if m != "buy&hold" and k == 6:
                st["excess_ci95_bps"] = [v * 1e4 for v in boot_mean(ex)]
            d["costs"][str(k)] = st
        rc, _, _ = simulate(o, c, dec[m], te_all, 6, fill="close_fill")
        d["close_fill_6bps_total_return"] = float(np.prod(1 + rc) - 1)
        r6, _, _ = simulate(o, c, dec[m], te_all, 6)
        d["by_year"] = {
            str(yr): float(
                np.prod(1 + r6[[j for j, t in enumerate(te_all) if df.date[t][:4] == str(yr)]]) - 1
            )
            for yr in yr_list
        }
        out["models"][m] = d
    return out


def run_comparison(config_path: Path, data_dir: Path, out_path: Path, symbols=None) -> dict:
    cfg = json.loads(Path(config_path).read_text())
    sha = hashlib.sha256(Path(config_path).read_bytes()).hexdigest()
    u = cfg["universe"]
    syms = symbols or [u["primary"], *u["exploratory"], u["benchmark"]]
    prov_path = Path(data_dir) / "PROVENANCE.json"
    res = dict(
        config_sha256=sha,
        config=cfg,
        provenance=json.loads(prov_path.read_text()) if prov_path.exists() else None,
        results=[run_symbol(s, cfg, data_dir) for s in syms],
    )
    Path(out_path).write_text(json.dumps(res, indent=1))
    return res


def main(argv=None) -> None:  # also reachable via `morning-star compare`
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, default=Path("configs/compare_v2.json"))
    p.add_argument("--data-dir", type=Path, default=Path("data"))
    p.add_argument("--out", type=Path, default=Path("results_compare.json"))
    a = p.parse_args(argv)
    res = run_comparison(a.config, a.data_dir, a.out)
    for r in res["results"]:
        print(r["symbol"], r["test_first"], r["test_last"], r["n_test"])
        for m, d in r["models"].items():
            s = d["costs"]["6"]
            print(
                f"  {m:15s} auc={d.get('auc', float('nan')):.3f} ret={s['total_return'] * 100:+.0f}% sharpe={s['sharpe']:.2f}"
            )


if __name__ == "__main__":
    main(sys.argv[1:])
