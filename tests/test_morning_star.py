"""morning-star artifact loads into crucibo replay."""

from __future__ import annotations

from pathlib import Path

from bar_ticks import make_price_series_ticks
from crucibo.io_parquet import ticks_to_parquet
from crucibo.morning_star.strategy import MorningStarStrategy
from crucibo.replay.engine import ReplayConfig, replay_ticks
from crucibo.replay.strategies import resolve_strategy


def _train_and_export_morning_star(parquet_path: Path, artifact_dir: Path) -> None:
    """Train via morning-star without adding it as a test dependency on import path."""
    import sys

    morning_star_src = Path(__file__).resolve().parents[2] / "morning-star" / "src"
    if str(morning_star_src) not in sys.path:
        sys.path.insert(0, str(morning_star_src))

    from morning_star.export.artifact import save_artifact
    from morning_star.train.loop import train_from_parquet

    model, ticks = train_from_parquet(
        ticks_path=parquet_path,
        seed=9,
        lookback=20,
        forward_horizon=5,
        epochs=20,
        target_shares=15,
    )
    save_artifact(
        model,
        artifact_dir,
        ticks_path=parquet_path,
        tick_count=len(ticks),
        symbol=ticks[0].symbol,
    )


def test_morning_star_strategy_from_artifact(tmp_path: Path) -> None:
    ticks = make_price_series_ticks(symbol="BTCUSDT", n=700, step=0.04)
    parquet_path = tmp_path / "bars.parquet"
    artifact_dir = tmp_path / "ms-artifact"
    ticks_to_parquet(ticks, parquet_path)
    _train_and_export_morning_star(parquet_path, artifact_dir)

    strat = resolve_strategy("morning_star", model_path=artifact_dir)
    cfg = ReplayConfig(slip_bps=0.0, fee_per_share=0.0, initial_cash=1_000_000.0)
    out_a = replay_ticks(strat, ticks, cfg)
    out_b = replay_ticks(MorningStarStrategy.from_artifact(artifact_dir), ticks, cfg)
    assert out_a.fills == out_b.fills
    assert out_a.final_shares == out_b.final_shares
