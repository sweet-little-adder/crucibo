"""Walk-forward: train on date range, score OOS slice, export artifact."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from morning_star.eval.replay import EvalConfig, replay_model, summarize_pnl
from morning_star.export.artifact import save_artifact
from morning_star.io_parquet import filter_price_bars, parquet_to_ticks, sorted_ticks
from morning_star.models.baseline import BaselineMLP
from morning_star.train.dataset import min_ticks_for_training
from morning_star.train.loop import train_baseline_mlp
from morning_star.train.split import split_ticks_by_date
from morning_star.train.torch_loop import train_torch_mlp

Backend = Literal["numpy", "torch"]


@dataclass(frozen=True)
class WalkForwardResult:
    model: BaselineMLP
    artifact_dir: Path
    train_tick_count: int
    oos_tick_count: int
    train_pnl: dict[str, float]
    oos_pnl: dict[str, float]
    report_path: Path


def run_walk_forward(
    *,
    ticks_path: Path,
    out_dir: Path,
    train_end: str,
    oos_start: str,
    backend: Backend = "numpy",
    seed: int = 42,
    lookback: int = 20,
    forward_horizon: int = 5,
    hidden_dim: int = 8,
    epochs: int = 80,
    learning_rate: float = 0.05,
    threshold: float = 0.5,
    target_shares: int = 50,
    initial_cash: float = 1_000_000.0,
    slip_bps: float = 2.0,
    fee_per_share: float = 0.005,
) -> WalkForwardResult:
    path = ticks_path.resolve()
    all_ticks = sorted_ticks(filter_price_bars(parquet_to_ticks(path)))
    train_ticks, oos_ticks = split_ticks_by_date(
        all_ticks,
        train_end=train_end,
        oos_start=oos_start,
    )
    need = min_ticks_for_training(lookback=lookback, forward_horizon=forward_horizon)
    if len(train_ticks) < need:
        raise ValueError(
            f"train window has {len(train_ticks)} ticks; need at least {need} "
            f"(lookback={lookback}, forward_horizon={forward_horizon})"
        )

    if backend == "torch":
        model = train_torch_mlp(
            train_ticks,
            lookback=lookback,
            forward_horizon=forward_horizon,
            hidden_dim=hidden_dim,
            epochs=epochs,
            learning_rate=learning_rate,
            seed=seed,
            threshold=threshold,
            target_shares=target_shares,
            initial_cash=initial_cash,
        )
    else:
        model = train_baseline_mlp(
            train_ticks,
            lookback=lookback,
            forward_horizon=forward_horizon,
            hidden_dim=hidden_dim,
            epochs=epochs,
            learning_rate=learning_rate,
            seed=seed,
            threshold=threshold,
            target_shares=target_shares,
            initial_cash=initial_cash,
        )

    eval_cfg = EvalConfig(
        initial_cash=initial_cash,
        slip_bps=slip_bps,
        fee_per_share=fee_per_share,
    )
    train_out = replay_model(model, train_ticks, eval_cfg)
    oos_out = replay_model(model, oos_ticks, eval_cfg)
    train_pnl = summarize_pnl(eval_cfg, train_out)
    oos_pnl = summarize_pnl(eval_cfg, oos_out)

    extra: dict[str, Any] = {
        "trainer": backend,
        "walk_forward": {
            "train_end": train_end,
            "oos_start": oos_start,
            "train_tick_count": len(train_ticks),
            "oos_tick_count": len(oos_ticks),
            "train_pnl_approx": train_pnl,
            "oos_pnl_approx": oos_pnl,
        },
    }
    artifact_dir = save_artifact(
        model,
        out_dir,
        ticks_path=path,
        tick_count=len(train_ticks),
        symbol=train_ticks[0].symbol if train_ticks else None,
        extra_manifest=extra,
    )
    report_path = artifact_dir / "walk_forward_report.json"
    report_path.write_text(
        json.dumps(extra["walk_forward"], indent=2) + "\n",
        encoding="utf-8",
    )
    return WalkForwardResult(
        model=model,
        artifact_dir=artifact_dir,
        train_tick_count=len(train_ticks),
        oos_tick_count=len(oos_ticks),
        train_pnl=train_pnl,
        oos_pnl=oos_pnl,
        report_path=report_path,
    )
