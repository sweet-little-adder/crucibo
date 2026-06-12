"""MLP training + checkpoint roundtrip."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from bar_ticks import make_price_series_ticks
from crucibo.io_parquet import ticks_to_parquet
from crucibo.mlp import load_mlp, train_from_parquet
from crucibo.replay.engine import ReplayConfig, replay_ticks
from crucibo.replay.strategies import NeuralStrategy


def test_train_save_load_roundtrip(tmp_path: Path) -> None:
    ticks = make_price_series_ticks(symbol="AAPL", n=500, step=0.1, dt_ns=60_000_000_000)
    parquet_path = tmp_path / "bars.parquet"
    out = tmp_path / "model.npz"
    ticks_to_parquet(ticks, parquet_path)
    model = train_from_parquet(
        ticks_path=parquet_path,
        out=out,
        seed=7,
        lookback=20,
        forward_horizon=5,
        epochs=20,
    )
    loaded = load_mlp(out)
    x = np.array([0.01, 0.0, 0.5, 0.0, 1.0])
    assert loaded.predict_proba(x) == model.predict_proba(x)


def test_train_from_parquet_roundtrip(tmp_path: Path) -> None:
    ticks = make_price_series_ticks(symbol="AAPL", n=600, step=0.08, dt_ns=60_000_000_000)
    parquet_path = tmp_path / "trades.parquet"
    out = tmp_path / "from_pq.npz"
    ticks_to_parquet(ticks, parquet_path)
    model = train_from_parquet(
        ticks_path=parquet_path,
        out=out,
        seed=5,
        lookback=20,
        forward_horizon=5,
        epochs=15,
    )
    loaded = load_mlp(out)
    x = np.array([0.01, 0.0, 0.5, 0.0, 1.0])
    assert loaded.predict_proba(x) == model.predict_proba(x)
    assert loaded.target_shares == model.target_shares


def test_train_from_parquet_too_few_ticks(tmp_path: Path) -> None:
    ticks = make_price_series_ticks(symbol="AAPL", n=10, dt_ns=1)
    parquet_path = tmp_path / "tiny.parquet"
    ticks_to_parquet(ticks, parquet_path)
    try:
        train_from_parquet(ticks_path=parquet_path, out=tmp_path / "x.npz", lookback=20)
    except ValueError as exc:
        assert "need at least" in str(exc)
    else:
        raise AssertionError("expected ValueError for too few ticks")


def test_neural_strategy_replay_deterministic(tmp_path: Path) -> None:
    ticks = make_price_series_ticks(symbol="AAPL", n=800, step=0.03, dt_ns=60_000_000_000)
    parquet_path = tmp_path / "bars.parquet"
    out = tmp_path / "model.npz"
    ticks_to_parquet(ticks, parquet_path)
    train_from_parquet(
        ticks_path=parquet_path,
        out=out,
        seed=11,
        lookback=20,
        forward_horizon=5,
        epochs=30,
        target_shares=20,
    )
    strat = NeuralStrategy.from_checkpoint(out)
    cfg = ReplayConfig(slip_bps=0.0, fee_per_share=0.0, initial_cash=1_000_000.0)
    out_a = replay_ticks(strat, ticks, cfg)
    out_b = replay_ticks(NeuralStrategy.from_checkpoint(out), ticks, cfg)
    assert out_a.fills == out_b.fills
    assert out_a.final_shares == out_b.final_shares
