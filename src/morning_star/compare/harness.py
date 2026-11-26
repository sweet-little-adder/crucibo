"""Comparison harness: features, walk-forward folds, next-open execution sim, metrics, block bootstrap.
Pure numpy/pandas. Mirrors morning-star feature schema v1 market features (tested for parity)."""

import math

import numpy as np
import pandas as pd

H = 5
LB = 20


def load(sym, root="data"):
    return pd.read_parquet(f"{root}/{sym}_daily_adj.parquet").reset_index(drop=True)


def features(close, lb=LB):
    """Vectorised morning-star schema v1 market features; row i uses close[:i+1] only. NaN until i>=lb."""
    c = np.asarray(close, float)
    n = len(c)
    X = np.full((n, 3), np.nan)
    lr = np.full(n, np.nan)
    lr[1:] = np.log(c[1:] / c[:-1])
    for i in range(lb, n):
        w = c[i - lb : i + 1]
        rets = lr[i - lb + 1 : i + 1]
        sm = w[1:].mean()
        var = ((w[1:] - sm) ** 2).mean()
        X[i] = [rets[-1], rets.mean(), (c[i] - sm) / (math.sqrt(var) + 1e-9)]
    return X


def labels(close, h=H):
    c = np.asarray(close, float)
    n = len(c)
    fwd = np.full(n, np.nan)
    fwd[: n - h] = np.log(c[h:] / c[: n - h])
    return fwd


class Scaler:
    def fit(self, X):
        self.mu = X.mean(0)
        self.sd = X.std(0) + 1e-12
        return self

    def tf(self, X):
        return (X - self.mu) / self.sd


def sigmoid(z):
    return 1 / (1 + np.exp(-np.clip(z, -60, 60)))


def train_mlp_v2(X, y, seed=42, hidden=8, epochs=300, lr=0.01, wd=1e-3):
    sc = Scaler().fit(X)
    Z = sc.tf(X)
    y = y.reshape(-1, 1)
    rng = np.random.default_rng(seed)
    d = Z.shape[1]
    P = dict(
        w1=rng.normal(0, 1 / math.sqrt(d), (d, hidden)),
        b1=np.zeros((1, hidden)),
        w2=rng.normal(0, 1 / math.sqrt(hidden), (hidden, 1)),
        b2=np.zeros((1, 1)),
    )
    m = {k: np.zeros_like(v) for k, v in P.items()}
    s = {k: np.zeros_like(v) for k, v in P.items()}
    n = len(Z)
    for t in range(1, epochs + 1):
        h = np.tanh(Z @ P["w1"] + P["b1"])
        p = sigmoid(h @ P["w2"] + P["b2"])
        e = (p - y) / n
        g2 = h.T @ e
        gb2 = e.sum(0, keepdims=True)
        gh = (e @ P["w2"].T) * (1 - h**2)
        g1 = Z.T @ gh
        gb1 = gh.sum(0, keepdims=True)
        G = dict(w1=g1 + wd * P["w1"], b1=gb1, w2=g2 + wd * P["w2"], b2=gb2)
        for k in P:
            m[k] = 0.9 * m[k] + 0.1 * G[k]
            s[k] = 0.999 * s[k] + 0.001 * G[k] ** 2
            P[k] -= lr * (m[k] / (1 - 0.9**t)) / (np.sqrt(s[k] / (1 - 0.999**t)) + 1e-8)
    return sc, P


def mlp_v2_proba(sc, P, X):
    return sigmoid(np.tanh(sc.tf(X) @ P["w1"] + P["b1"]) @ P["w2"] + P["b2"]).reshape(-1)


def fold_slices(dates, years, min_rows, valid):
    """yield (year, train_idx, test_idx). Train rows must have their label window end before test year starts."""
    yr = np.array([int(d[:4]) for d in dates])
    out = []
    for y in years:
        te = np.where(yr == y)[0]
        if len(te) == 0:
            continue
        start = te[0]
        tr = np.where(valid & (np.arange(len(dates)) + H < start))[0]  # purge: i+H < start
        if len(tr) < min_rows:
            continue
        out.append((y, tr, te))
    return out


def simulate(o, c, pos, test_idx, cost_bps, fill="next_open"):
    """Long/flat, whole-account sizing decided at the signal close, with explicit cash and shares.

    pos[j] is the decision at the close of bar test_idx[j] (contiguous bars). Returns per-period
    returns, trade sides per period and the held-position indicator after each decision.

    next_open: trade at open[t+1]. On entry, shares = cash / close[t] (the share count a trader can
    size when the signal fires). If the open gaps down, part of the cash stays idle; if it gaps up,
    the buy is clamped to the cash available. Shares are then held (no rebalancing) until the signal
    turns flat. Each period runs open[t+1] -> open[t+2] (last bar: to close). This is the same
    convention crucibo's ArtifactModelStrategy(sizing="equity") + run_backtest(latency_bars=1,
    clamp_buys_to_cash=True) uses.
    close_fill (crucibo tick-replay style): trade at close[t], period close[t] -> close[t+1].
    Costs: cost_bps is the total per side, split 2/3 fee (on gross) and 1/3 slippage (on price),
    i.e. 6 bps = crucibo's 4 fee + 2 slippage. Any open position is liquidated at the final close.
    """
    n = len(c)
    fee = cost_bps * (2 / 3) / 1e4
    slip = cost_bps * (1 / 3) / 1e4
    cash, shares, eq_prev = 1.0, 0.0, 1.0
    ret = np.zeros(len(test_idx))
    turn = np.zeros(len(test_idx))
    held = np.zeros(len(test_idx))
    for j, t in enumerate(test_idx):
        if t + 1 < n:
            ref = o[t + 1] if fill == "next_open" else c[t]
            want = pos[j] > 0
            if want and shares == 0.0:
                px = ref * (1 + slip)
                shares = min(cash / c[t], cash / (px * (1 + fee)))
                cash -= shares * px * (1 + fee)
                turn[j] += 1
            elif (not want) and shares > 0.0:
                cash += shares * ref * (1 - slip) * (1 - fee)
                shares = 0.0
                turn[j] += 1
            if fill == "next_open":
                mark = o[t + 2] if t + 2 < n else c[n - 1]
            else:
                mark = c[t + 1]
        else:
            mark = c[n - 1]
        eq = cash + shares * mark
        ret[j] = eq / eq_prev - 1
        eq_prev = eq
        held[j] = 1.0 if shares > 0 else 0.0
    if shares > 0.0:  # terminal liquidation at the last mark (the final close when the test window ends at the last bar)
        eq_final = cash + shares * mark * (1 - slip) * (1 - fee)
        ret[-1] = (1 + ret[-1]) * eq_final / eq_prev - 1
        turn[-1] += 1
    return ret, turn, held


def stats(ret, turn, pos):
    eq = np.concatenate([[1.0], np.cumprod(1 + ret)])
    dd = (eq / np.maximum.accumulate(eq) - 1).min()
    sd = ret.std()
    sh = ret.mean() / sd * math.sqrt(252) if sd > 0 else 0.0
    yrs = len(ret) / 252
    return dict(
        total_return=float(eq[-1] - 1),
        cagr=float(eq[-1] ** (1 / yrs) - 1),
        sharpe=float(sh),
        max_dd=float(dd),
        round_trip_sides_per_year=float(turn.sum() / yrs),
        exposure=float(np.mean(pos)),
    )


def auc(score, y):
    s = pd.Series(score).rank().values
    n1 = y.sum()
    n0 = len(y) - n1
    return (
        float((s[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))
        if n1 > 0 and n0 > 0
        else float("nan")
    )


def block_idx(n, block, rng):
    nb = math.ceil(n / block)
    st = rng.integers(0, n - block + 1, nb)
    return (st[:, None] + np.arange(block)).reshape(-1)[:n]


def boot_auc(score, y, B=2000, block=21, seed=7):
    rng = np.random.default_rng(seed)
    v = []
    for _ in range(B):
        i = block_idx(len(y), block, rng)
        a = auc(score[i], y[i])
        if not math.isnan(a):
            v.append(a)
    return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))


def boot_mean(x, B=2000, block=21, seed=7):
    rng = np.random.default_rng(seed)
    v = [x[block_idx(len(x), block, rng)].mean() for _ in range(B)]
    return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))
