"""Load persisted backtest run bundles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from crucibo.replay.bundle import default_runs_parent


@dataclass(frozen=True)
class BacktestRun:
    run_id: str
    dir: Path
    manifest: dict
    equity_curve: list[dict[str, float | int]]
    fills: list[dict]


def runs_dir(*, data_root: Path | None = None) -> Path:
    root = data_root or default_runs_parent()
    return (root / "runs").resolve()


def list_backtest_runs(*, data_root: Path | None = None) -> list[Path]:
    base = runs_dir(data_root=data_root)
    if not base.is_dir():
        return []
    dirs = [p for p in base.iterdir() if p.is_dir() and p.name.startswith("bt_")]
    return sorted(dirs, key=lambda p: p.stat().st_mtime, reverse=True)


def resolve_run_dir(*, run_id: str, data_root: Path | None = None) -> Path:
    rid = run_id.strip()
    if rid.lower() == "latest":
        candidates = list_backtest_runs(data_root=data_root)
        if not candidates:
            raise FileNotFoundError("no backtest runs found under data/runs (bt_*)")
        return candidates[0]

    base = runs_dir(data_root=data_root)
    direct = (base / rid).resolve()
    if direct.is_dir():
        return direct

    matches = sorted(base.glob(f"*{rid}*"))
    dirs = [p for p in matches if p.is_dir()]
    if len(dirs) == 1:
        return dirs[0].resolve()
    if len(dirs) > 1:
        raise ValueError(f"ambiguous run id {run_id!r}: {[p.name for p in dirs]}")
    raise FileNotFoundError(f"run not found: {run_id!r} (looked in {base})")


def load_backtest_run(*, run_dir: Path) -> BacktestRun:
    path = run_dir.resolve()
    manifest_path = path / "run_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing run_manifest.json in {path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_id = str(manifest.get("run_id", path.name))

    eq_path = path / "equity_curve.parquet"
    fills_path = path / "fills.parquet"
    if not eq_path.is_file():
        raise FileNotFoundError(f"missing equity_curve.parquet in {path}")

    equity_df = pl.read_parquet(eq_path)
    equity_curve = equity_df.to_dicts()

    fills: list[dict] = []
    if fills_path.is_file():
        fills = pl.read_parquet(fills_path).to_dicts()

    return BacktestRun(
        run_id=run_id,
        dir=path,
        manifest=manifest,
        equity_curve=equity_curve,
        fills=fills,
    )