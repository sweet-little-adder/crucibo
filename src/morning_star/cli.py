"""morning-star CLI — train, walk-forward, export artifacts for crucibo."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from morning_star.config import load_config, merge_config
from morning_star.export.artifact import save_artifact
from morning_star.train.loop import train_from_parquet
from morning_star.train.torch_loop import train_torch_mlp
from morning_star.train.walk_forward import run_walk_forward


def _train_kwargs_from_args(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    merged = merge_config(
        config,
        {
            "seed": args.seed,
            "lookback": args.lookback,
            "forward_horizon": args.forward_horizon,
            "hidden_dim": args.hidden_dim,
            "epochs": args.epochs,
            "learning_rate": args.learning_rate,
            "threshold": args.threshold,
            "target_shares": args.target_shares,
            "initial_cash": args.initial_cash,
        },
    )
    return {
        "seed": int(merged.get("seed", 42)),
        "lookback": int(merged.get("lookback", 20)),
        "forward_horizon": int(merged.get("forward_horizon", 5)),
        "hidden_dim": int(merged.get("hidden_dim", 8)),
        "epochs": int(merged.get("epochs", 80)),
        "learning_rate": float(merged.get("learning_rate", 0.05)),
        "threshold": float(merged.get("threshold", 0.5)),
        "target_shares": int(merged.get("target_shares", 50)),
        "initial_cash": float(merged.get("initial_cash", 1_000_000.0)),
    }


def _add_train_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, default=None, help="YAML defaults")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--lookback", type=int, default=None)
    parser.add_argument("--forward-horizon", type=int, default=None)
    parser.add_argument("--hidden-dim", type=int, default=None)
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--learning-rate", type=float, default=None)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--target-shares", type=int, default=None)
    parser.add_argument("--initial-cash", type=float, default=None)
    parser.add_argument(
        "--backend",
        choices=["numpy", "torch"],
        default="numpy",
        help="numpy: pure SGD; torch: PyTorch trainer (exports numpy weights)",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="morning-star",
        description="Train models and export crucibo-compatible artifacts.",
    )
    subs = parser.add_subparsers(dest="cmd", required=True)

    p_train = subs.add_parser("train", help="Train MLP from crucibo Parquet ticks")
    p_train.add_argument("--ticks", type=Path, required=True)
    p_train.add_argument("--out", type=Path, required=True, help="Artifact directory")
    _add_train_flags(p_train)

    p_wf = subs.add_parser(
        "walk-forward",
        help="Train on date range ending train-end, score OOS from oos-start",
    )
    p_wf.add_argument("--ticks", type=Path, required=True)
    p_wf.add_argument("--out", type=Path, required=True, help="Artifact directory")
    p_wf.add_argument("--train-end", required=True, help="Last train day YYYY-MM-DD (inclusive)")
    p_wf.add_argument("--oos-start", required=True, help="First OOS day YYYY-MM-DD (inclusive)")
    p_wf.add_argument("--slip-bps", type=float, default=2.0)
    p_wf.add_argument("--fee-per-share", type=float, default=0.005)
    _add_train_flags(p_wf)

    args = parser.parse_args()
    config = load_config(getattr(args, "config", None))
    train_kwargs = _train_kwargs_from_args(args, config)
    backend = getattr(args, "backend", "numpy")

    try:
        if args.cmd == "train":
            if backend == "torch":
                from morning_star.io_parquet import parquet_to_ticks, sorted_ticks
                from morning_star.train.dataset import min_ticks_for_training

                path = args.ticks.resolve()
                ticks = sorted_ticks(parquet_to_ticks(path))
                need = min_ticks_for_training(
                    lookback=train_kwargs["lookback"],
                    forward_horizon=train_kwargs["forward_horizon"],
                )
                if len(ticks) < need:
                    raise ValueError(f"parquet has {len(ticks)} ticks; need at least {need}")
                model = train_torch_mlp(ticks, **train_kwargs)
                artifact_dir = save_artifact(
                    model,
                    args.out,
                    ticks_path=path,
                    tick_count=len(ticks),
                    symbol=ticks[0].symbol if ticks else None,
                    extra_manifest={"trainer": "torch"},
                )
            else:
                model, ticks = train_from_parquet(ticks_path=args.ticks, **train_kwargs)
                artifact_dir = save_artifact(
                    model,
                    args.out,
                    ticks_path=args.ticks,
                    tick_count=len(ticks),
                    symbol=ticks[0].symbol if ticks else None,
                    extra_manifest={"trainer": "numpy"},
                )
            print("artifact:", artifact_dir)
            print(
                json.dumps(
                    {
                        "backend": backend,
                        "lookback": model.lookback,
                        "target_shares": model.target_shares,
                        "hidden_dim": model.hidden_dim,
                    }
                )
            )
            return

        if args.cmd == "walk-forward":
            result = run_walk_forward(
                ticks_path=args.ticks,
                out_dir=args.out,
                train_end=args.train_end,
                oos_start=args.oos_start,
                backend=backend,
                slip_bps=args.slip_bps,
                fee_per_share=args.fee_per_share,
                **train_kwargs,
            )
            print("artifact:", result.artifact_dir)
            print("report:", result.report_path)
            print(
                json.dumps(
                    {
                        "backend": backend,
                        "train_ticks": result.train_tick_count,
                        "oos_ticks": result.oos_tick_count,
                        "train_pnl": result.train_pnl,
                        "oos_pnl": result.oos_pnl,
                    }
                )
            )
            return

        parser.error(f"unknown {args.cmd!r}")
    except (ValueError, ImportError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
