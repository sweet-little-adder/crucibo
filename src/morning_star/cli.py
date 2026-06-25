"""morning-star CLI — train and export artifact bundles."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from morning_star.export.artifact import save_artifact
from morning_star.train.loop import train_from_parquet


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="morning-star",
        description="Train baseline models and export crucibo-compatible artifacts.",
    )
    subs = parser.add_subparsers(dest="cmd", required=True)

    p_train = subs.add_parser("train", help="Train baseline MLP from crucibo Parquet ticks")
    p_train.add_argument("--ticks", type=Path, required=True, help="Input bars.parquet path")
    p_train.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output artifact directory (manifest.json + weights.npz)",
    )
    p_train.add_argument("--seed", type=int, default=42)
    p_train.add_argument("--lookback", type=int, default=20)
    p_train.add_argument("--forward-horizon", type=int, default=5)
    p_train.add_argument("--hidden-dim", type=int, default=8)
    p_train.add_argument("--epochs", type=int, default=80)
    p_train.add_argument("--learning-rate", type=float, default=0.05)
    p_train.add_argument("--threshold", type=float, default=0.5)
    p_train.add_argument("--target-shares", type=int, default=50)
    p_train.add_argument("--initial-cash", type=float, default=1_000_000.0)

    args = parser.parse_args()

    if args.cmd != "train":
        parser.error(f"unknown {args.cmd!r}")

    try:
        model, ticks = train_from_parquet(
            ticks_path=args.ticks,
            seed=args.seed,
            lookback=args.lookback,
            forward_horizon=args.forward_horizon,
            hidden_dim=args.hidden_dim,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            threshold=args.threshold,
            target_shares=args.target_shares,
            initial_cash=args.initial_cash,
        )
        artifact_dir = save_artifact(
            model,
            args.out,
            ticks_path=args.ticks,
            tick_count=len(ticks),
            symbol=ticks[0].symbol if ticks else None,
        )
    except ValueError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2) from exc

    print("artifact:", artifact_dir)
    print(
        json.dumps(
            {
                "lookback": model.lookback,
                "forward_horizon": model.forward_horizon,
                "threshold": model.threshold,
                "target_shares": model.target_shares,
                "hidden_dim": model.hidden_dim,
                "training_tick_count": len(ticks),
            }
        )
    )


if __name__ == "__main__":
    main()
