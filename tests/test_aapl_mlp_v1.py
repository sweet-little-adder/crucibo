"""aapl_mlp_v1 artifact loads into crucibo replay."""

from __future__ import annotations

import sys
from pathlib import Path

from bar_ticks import make_price_series_ticks
from crucibo.aapl_mlp_v1.strategy import AaplMlpV1Strategy
from crucibo.io_parquet import ticks_to_parquet
from crucibo.replay.engine import ReplayConfig, replay_ticks
from crucibo.replay.strategies import resolve_strategy


def _train_and_export_artifact(parquet_path: Path, artifact_dir: Path, *, symbol: str) -> None:
    """Train via trainer repo without adding it as a test dependency on import path."""
    trainer_src = Path(__file__).resolve().parents[2] / "morning-star" / "src"
    if str(trainer_src) not in sys.path:
        sys.path.insert(0, str(trainer_src))

    from morning_star.export.artifact import save_artifact
    from morning_star.train.loop import train_from_parquet

    model, trained_ticks = train_from_parquet(ticks_path=parquet_path, seed=42, epochs=15)
    save_artifact(
        model,
        artifact_dir,
        ticks_path=parquet_path,
        tick_count=len(trained_ticks),
        symbol=symbol,
    )


def test_aapl_mlp_v1_strategy_from_artifact(tmp_path: Path) -> None:
    ticks = make_price_series_ticks(n=40)
    parquet_path = tmp_path / "bars.parquet"
    ticks_to_parquet(ticks, parquet_path)
    artifact_dir = tmp_path / "artifact"
    _train_and_export_artifact(parquet_path, artifact_dir, symbol=ticks[0].symbol)

    strat = resolve_strategy("aapl_mlp_v1", model_path=artifact_dir)
    cfg = ReplayConfig(initial_cash=1_000_000.0, slip_bps=0.0, fee_per_share=0.0)
    out_a = replay_ticks(strat, ticks, cfg)
    out_b = replay_ticks(AaplMlpV1Strategy.from_artifact(artifact_dir), ticks, cfg)
    assert out_a.final_cash == out_b.final_cash
    assert out_a.final_shares == out_b.final_shares