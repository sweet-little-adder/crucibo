"""Harness correctness: feature parity, no lookahead, purge, train-only scaling, cost accounting."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("pandas")

from morning_star.compare.harness import (  # noqa: E402
    H,
    Scaler,
    features,
    fold_slices,
    simulate,
    stats,
)
from morning_star.features.builder import FeatureState  # noqa: E402
from morning_star.ticks import Tick  # noqa: E402

rng = np.random.default_rng(0)
CLOSE = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 400)))
OPEN = CLOSE * np.exp(rng.normal(0, 0.003, 400))


def test_features_match_morning_star_featurestate():
    st = FeatureState(lookback=20, initial_cash=1e6, max_position=1)
    X = features(CLOSE)
    for i, p in enumerate(CLOSE):
        tick = Tick(ts_event_ns=i + 1, symbol="S", price=float(p), size=1)
        v = st.update(tick, position=0, cash=1e6)
        if v is None:
            assert np.isnan(X[i]).all()
        else:
            np.testing.assert_allclose(X[i], v[:3], rtol=1e-12)


def test_features_no_lookahead():
    c2 = CLOSE.copy()
    c2[250:] *= 3
    np.testing.assert_array_equal(features(CLOSE)[:250], features(c2)[:250])


def test_label_purge_and_fold_order():
    dates = pd.date_range("2015-01-01", periods=1500, freq="B").strftime("%Y-%m-%d").values
    folds = fold_slices(dates, [2018, 2019, 2020], 100, np.ones(1500, bool))
    assert folds
    for _year, tr, te in folds:
        assert tr.max() + H < te.min()  # last train label window ends before the test year
        assert set(tr).isdisjoint(te)


def test_scaler_uses_train_only():
    a = rng.normal(size=(200, 3))
    b = a * 100
    s = Scaler().fit(a)
    np.testing.assert_allclose(s.mu, a.mean(0))
    np.testing.assert_allclose(s.tf(b), (b - a.mean(0)) / (a.std(0) + 1e-12))


def test_buyhold_zero_cost_sizes_at_signal_close_fills_at_open():
    idx = np.arange(50, 300)
    r, _, _ = simulate(OPEN, CLOSE, np.ones(len(idx)), idx, 0)
    shares = min(1.0 / CLOSE[50], 1.0 / OPEN[51])  # sized at signal close, clamped to cash
    expected = 1.0 + shares * (OPEN[301] - OPEN[51])
    assert abs(np.prod(1 + r) - expected) < 1e-9


def test_buyhold_costs_entry_and_exit():
    idx = np.arange(50, 300)
    r0, _, _ = simulate(OPEN, CLOSE, np.ones(len(idx)), idx, 0)
    r1, t, _ = simulate(OPEN, CLOSE, np.ones(len(idx)), idx, 10)
    assert t.sum() == 2.0  # one entry, one terminal exit
    ratio = np.prod(1 + r1) / np.prod(1 + r0)
    assert 0.9975 < ratio < 0.9995  # about 2 x 10 bps on the invested part


def test_gap_down_leaves_cash_idle_gap_up_clamps_to_cash():
    c = np.full(20, 100.0)
    idx = np.arange(6, 11)
    pos = np.array([0, 0, 0, 0, 1.0])  # signal at bar 10, fill at open 11
    o = np.full(20, 100.0)
    o[11] = 80.0  # gap down: 1 share-unit of cash/100 bought, 20% of cash idle
    r, _, held = simulate(o, c, pos, idx, 0, )
    assert held[4] == 1.0
    assert abs(r[4] - 0.01 * (100.0 - 80.0)) < 1e-12  # only 1% of 100 units, marked at open 12
    o2 = np.full(20, 100.0)
    o2[11] = 125.0  # gap up: clamp to cash, never more than 100% of equity
    shares_cap = 1.0 / 125.0
    r2, _, _ = simulate(o2, c, pos, idx, 0)
    assert abs(r2[4] - shares_cap * (100.0 - 125.0)) < 1e-12


def test_flat_has_no_pnl_or_cost():
    idx = np.arange(50, 300)
    r, t, _ = simulate(OPEN, CLOSE, np.zeros(len(idx)), idx, 10)
    assert np.all(r == 0) and t.sum() == 0


def test_signal_executes_next_open_not_same_close():
    idx = np.arange(100, 110)
    pos = np.zeros(10)
    pos[3] = 1  # signal at bar 103 -> buy at open 104, sell (flat signal) at open 105
    r, turn, _ = simulate(OPEN, CLOSE, pos, idx, 0)
    shares = min(1.0 / CLOSE[103], 1.0 / OPEN[104])
    exp_period = (1.0 - shares * OPEN[104] + shares * OPEN[105]) / 1.0 - 1
    assert abs(r[3] - exp_period) < 1e-12
    assert turn.sum() == 2 and np.count_nonzero(r[:3]) == 0


def test_continuity_across_folds_charges_no_extra_round_trip():
    _, t, _ = simulate(OPEN, CLOSE, np.ones(100), np.arange(100, 200), 6)
    assert t.sum() == 2


def test_drawdown_includes_start():
    s = stats(np.array([-0.1, 0.0]), np.array([0, 0]), np.array([1, 1]))
    assert abs(s["max_dd"] + 0.1) < 1e-12
