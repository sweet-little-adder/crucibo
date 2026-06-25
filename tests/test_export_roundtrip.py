"""Artifact export + reload roundtrip."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

from morning_star.export.artifact import load_baseline_mlp, load_manifest, save_artifact
from morning_star.train.loop import train_from_parquet
from tick_fixtures import make_price_series_ticks


def _write_parquet(ticks, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = {
        "ts_event_ns": [t.ts_event_ns for t in ticks],
        "ts_ingest_ns": [t.ts_ingest_ns for t in ticks],
        "symbol": [t.symbol for t in ticks],
        "price": [t.price for t in ticks],
        "size": [t.size for t in ticks],
        "conditions": [t.conditions for t in ticks],
        "schema_version": [1 for _ in ticks],
    }
    pl.DataFrame(rows).write_parquet(path)


def test_export_roundtrip(tmp_path: Path) -> None:
    ticks = make_price_series_ticks(symbol="BTCUSDT", n=600, step=0.08)
    parquet_path = tmp_path / "bars.parquet"
    artifact_dir = tmp_path / "artifact"
    _write_parquet(ticks, parquet_path)

    model, trained_ticks = train_from_parquet(
        ticks_path=parquet_path,
        seed=3,
        lookback=20,
        forward_horizon=5,
        epochs=15,
    )
    save_artifact(
        model,
        artifact_dir,
        ticks_path=parquet_path,
        tick_count=len(trained_ticks),
        symbol="BTCUSDT",
    )

    manifest = load_manifest(artifact_dir / "manifest.json")
    assert manifest.training_symbol == "BTCUSDT"
    loaded = load_baseline_mlp(artifact_dir)
    x = np.array([0.01, 0.0, 0.5, 0.0, 1.0])
    assert loaded.predict_proba(x) == model.predict_proba(x)
