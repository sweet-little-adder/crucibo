"""Command-line entry (batch workflows)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

from crucibo.alphavantage.bars import ingest_alpha_vantage_daily, ingest_alpha_vantage_intraday
from crucibo.binance.klines import ingest_binance_futures
from crucibo.io_parquet import filter_price_bars, parquet_to_ticks
from crucibo.mlp import train_from_parquet
from crucibo.news.feeds import list_feeds
from crucibo.news.rss import ingest_all_feeds_day, ingest_rss_feed_day
from crucibo.polygon.trades import ingest_polygon_trades_day
from crucibo.replay.bundle import default_runs_parent, make_run_id, write_run_bundle
from crucibo.replay.engine import ReplayConfig, replay_ticks, summarize_pnl
from crucibo.replay.strategies import resolve_strategy


def _git_sha_optional() -> str | None:
    return os.environ.get("CRUCIBO_GIT_SHA", "").strip() or None


def _runs_parent(cli_root: Path | None) -> Path:
    return Path(cli_root).resolve() if cli_root else default_runs_parent()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="crucibo",
        description=(
            "US equities ingest + replay on real market data — "
            "read docs/HANDOFF.md for continuity when Cursor is closed."
        ),
    )
    subs = parser.add_subparsers(dest="cmd", required=True)

    p_avd = subs.add_parser(
        "alphavantage-daily",
        help="Alpha Vantage daily bars (~100 days, 1 free API call)",
    )
    p_avd.add_argument("--symbol", required=True)
    p_avd.add_argument("--data-root", type=Path, default=None)

    p_avi = subs.add_parser(
        "alphavantage-intraday",
        help="Alpha Vantage intraday bars (~100 bars, 1 free API call — 15-min delayed)",
    )
    p_avi.add_argument("--symbol", required=True)
    p_avi.add_argument(
        "--interval",
        default="5min",
        choices=["1min", "5min", "15min", "30min", "60min"],
    )
    p_avi.add_argument(
        "--date",
        dest="day",
        default=None,
        help="Optional filter YYYY-MM-DD (must fall inside compact window)",
    )
    p_avi.add_argument("--data-root", type=Path, default=None)

    p_bin = subs.add_parser(
        "ingest-binance",
        help="Binance USD-M futures klines + mark price + funding (public API, no key)",
    )
    p_bin.add_argument("--symbol", required=True, help="Perpetual symbol, e.g. BTCUSDT")
    p_bin.add_argument(
        "--interval",
        default="5m",
        choices=[
            "1m",
            "3m",
            "5m",
            "15m",
            "30m",
            "1h",
            "2h",
            "4h",
            "6h",
            "8h",
            "12h",
            "1d",
            "3d",
            "1w",
            "1M",
        ],
    )
    p_bin.add_argument(
        "--start-date",
        required=True,
        help="UTC start calendar day YYYY-MM-DD (inclusive)",
    )
    p_bin.add_argument(
        "--end-date",
        default=None,
        help="UTC end calendar day YYYY-MM-DD (inclusive); default = now",
    )
    p_bin.add_argument(
        "--no-mark-price",
        action="store_true",
        help="Skip mark-price klines",
    )
    p_bin.add_argument(
        "--no-funding",
        action="store_true",
        help="Skip funding-rate history",
    )
    p_bin.add_argument("--data-root", type=Path, default=None)

    p_poly = subs.add_parser(
        "polygon-trades",
        help="Polygon REST v3 trades ingest (paid entitlement required)",
    )
    p_poly.add_argument("--symbol", required=True)
    p_poly.add_argument("--date", dest="day", required=True)
    p_poly.add_argument("--data-root", type=Path, default=None)

    p_rp = subs.add_parser(
        "replay-parquet",
        help="Replay from bars.parquet or trades.parquet on disk",
    )
    p_rp.add_argument("--ticks", type=Path, required=True)
    p_rp.add_argument("--strategy", default="flat", help="flat | buy_hold | neural | morning_star")
    p_rp.add_argument("--target-shares", type=int, default=100)
    p_rp.add_argument(
        "--model",
        type=Path,
        default=None,
        help="neural: .npz checkpoint; morning_star: artifact dir (manifest.json + weights.npz)",
    )
    p_rp.add_argument("--slip-bps", type=float, default=2.0)
    p_rp.add_argument("--fee-per-share", type=float, default=0.005)
    p_rp.add_argument("--initial-cash", type=float, default=1_000_000.0)
    p_rp.add_argument("--run-id", default=None)
    p_rp.add_argument("--data-root", type=Path, default=None)

    p_tp = subs.add_parser(
        "train-from-parquet",
        help="Train MLP checkpoint from bars.parquet or trades.parquet",
    )
    p_tp.add_argument("--ticks", type=Path, required=True, help="Input parquet")
    p_tp.add_argument("--out", type=Path, required=True, help="Output .npz path")
    p_tp.add_argument("--seed", type=int, default=42)
    p_tp.add_argument("--lookback", type=int, default=20)
    p_tp.add_argument("--forward-horizon", type=int, default=5)
    p_tp.add_argument("--hidden-dim", type=int, default=8)
    p_tp.add_argument("--epochs", type=int, default=80)
    p_tp.add_argument("--learning-rate", type=float, default=0.05)
    p_tp.add_argument("--threshold", type=float, default=0.5)
    p_tp.add_argument("--target-shares", type=int, default=50)
    p_tp.add_argument("--initial-cash", type=float, default=1_000_000.0)

    p_paper = subs.add_parser(
        "paper-binance",
        help="Paper trade on live Binance USD-M kline closes (no real orders)",
    )
    p_paper.add_argument("--symbol", required=True, help="Perpetual symbol, e.g. BTCUSDT")
    p_paper.add_argument(
        "--interval",
        default="5m",
        choices=["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"],
    )
    p_paper.add_argument(
        "--strategy",
        default="flat",
        help="flat | buy_hold | morning_star",
    )
    p_paper.add_argument("--target-shares", type=int, default=1)
    p_paper.add_argument(
        "--model",
        type=Path,
        default=None,
        help="morning_star artifact dir (manifest.json + weights.npz)",
    )
    p_paper.add_argument("--slip-bps", type=float, default=2.0)
    p_paper.add_argument("--fee-per-share", type=float, default=0.0)
    p_paper.add_argument("--initial-cash", type=float, default=1_000_000.0)
    p_paper.add_argument(
        "--max-loss-usd",
        type=float,
        default=None,
        help="Kill switch: stop if drawdown from equity peak exceeds this USD amount",
    )
    p_paper.add_argument("--max-position-shares", type=int, default=None)
    p_paper.add_argument(
        "--max-ticks",
        type=int,
        default=None,
        help="Stop after N closed klines (useful for smoke tests)",
    )
    p_paper.add_argument("--run-id", default=None)
    p_paper.add_argument("--data-root", type=Path, default=None)

    p_rf = subs.add_parser("rss-feeds", help="List curated free RSS news feeds (no network)")
    p_rf.add_argument("--json", action="store_true", help="Emit machine-readable feed list")

    p_ri = subs.add_parser(
        "rss-ingest",
        help="Ingest RSS/Atom headlines for one UTC day (free — respect feed ToS)",
    )
    p_ri.add_argument("--date", dest="day", required=True, help="UTC calendar day YYYY-MM-DD")
    p_ri.add_argument("--source", default=None, help="Feed id from rss-feeds")
    p_ri.add_argument("--all", action="store_true", help="Ingest every curated feed for --date")
    p_ri.add_argument("--feed-url", default=None, help="Custom feed URL")
    p_ri.add_argument("--data-root", type=Path, default=None)

    args = parser.parse_args()

    if args.cmd == "rss-feeds":
        feeds = list_feeds()
        if args.json:
            print(
                json.dumps(
                    [
                        {
                            "source_id": feed.source_id,
                            "name": feed.name,
                            "url": feed.url,
                            "description": feed.description,
                        }
                        for feed in feeds
                    ],
                    indent=2,
                )
            )
        else:
            for feed in feeds:
                print(f"{feed.source_id:16}  {feed.name}")
                print(f"{'':16}  {feed.url}")
        return

    if args.cmd == "rss-ingest":
        if args.all and (args.source or args.feed_url):
            print("use either --all or --source/--feed-url, not both", file=sys.stderr)
            raise SystemExit(2)
        if not args.all and not args.source and not args.feed_url:
            print("provide --source, --feed-url, or --all", file=sys.stderr)
            raise SystemExit(2)
        try:
            if args.all:
                outcomes = ingest_all_feeds_day(day=args.day, silver_root=args.data_root)
                total = sum(outcome.row_count for outcome in outcomes)
                print(total, "articles across", len(outcomes), "feeds for", args.day)
                for outcome in outcomes:
                    print(outcome.row_count, "→", outcome.parquet_path)
                return
            outcome = ingest_rss_feed_day(
                day=args.day,
                source_id=args.source,
                feed_url=args.feed_url,
                silver_root=args.data_root,
            )
        except (ValueError, httpx.HTTPError) as exc:
            print(exc, file=sys.stderr)
            raise SystemExit(2) from exc
        print(outcome.row_count, "articles →", outcome.parquet_path)
        print("manifest:", outcome.manifest_path)
        return

    if args.cmd == "train-from-parquet":
        try:
            model = train_from_parquet(
                ticks_path=args.ticks,
                out=args.out,
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
        except ValueError as exc:
            print(exc, file=sys.stderr)
            raise SystemExit(2) from exc
        print("model:", args.out.resolve())
        print("ticks:", args.ticks.resolve())
        print(
            json.dumps(
                {
                    "lookback": model.lookback,
                    "forward_horizon": model.forward_horizon,
                    "threshold": model.threshold,
                    "target_shares": model.target_shares,
                    "hidden_dim": model.hidden_dim,
                }
            )
        )
        return

    if args.cmd == "ingest-binance":
        try:
            out = ingest_binance_futures(
                symbol=args.symbol,
                interval=args.interval,
                start_date=args.start_date,
                end_date=args.end_date,
                silver_root=args.data_root,
                include_mark_price=not args.no_mark_price,
                include_funding=not args.no_funding,
            )
        except (RuntimeError, ValueError, httpx.HTTPError) as exc:
            print(exc, file=sys.stderr)
            raise SystemExit(2) from exc
        print(
            out.row_count,
            "events →",
            out.parquet_path,
            f"(klines={out.kline_count}, mark={out.mark_price_count}, funding={out.funding_count})",
        )
        print("manifest:", out.manifest_path)
        return

    if args.cmd == "polygon-trades":
        try:
            out = ingest_polygon_trades_day(
                symbol=args.symbol,
                day=args.day,
                silver_root=args.data_root,
            )
        except RuntimeError as exc:
            print(exc, file=sys.stderr)
            raise SystemExit(2) from exc
        print(out.row_count, "ticks →", out.parquet_path)
        print("manifest:", out.manifest_path)
        return

    if args.cmd == "alphavantage-daily":
        try:
            out = ingest_alpha_vantage_daily(symbol=args.symbol, silver_root=args.data_root)
        except (RuntimeError, httpx.HTTPError) as exc:
            print(exc, file=sys.stderr)
            raise SystemExit(2) from exc
        print(out.row_count, "daily bars →", out.parquet_path)
        print("manifest:", out.manifest_path)
        print(
            "tip: split train/OOS by date, then replay-parquet / train-from-parquet",
            file=sys.stderr,
        )
        return

    if args.cmd == "alphavantage-intraday":
        try:
            out = ingest_alpha_vantage_intraday(
                symbol=args.symbol,
                interval=args.interval,
                day=args.day,
                silver_root=args.data_root,
            )
        except (RuntimeError, ValueError, httpx.HTTPError) as exc:
            print(exc, file=sys.stderr)
            raise SystemExit(2) from exc
        print(out.row_count, "intraday bars →", out.parquet_path)
        print("manifest:", out.manifest_path)
        return

    if args.cmd == "paper-binance":
        import asyncio

        from crucibo.paper.engine import PaperConfig
        from crucibo.paper.session import run_paper_session, write_paper_manifest

        runs_parent = _runs_parent(args.data_root)
        try:
            strat = resolve_strategy(
                args.strategy,
                target_shares=args.target_shares,
                model_path=args.model,
            )
        except ValueError as exc:
            print(exc, file=sys.stderr)
            raise SystemExit(2) from exc

        cfg = PaperConfig(
            initial_cash=args.initial_cash,
            slip_bps=args.slip_bps,
            fee_per_share=args.fee_per_share,
            max_loss_usd=args.max_loss_usd,
            max_position_shares=args.max_position_shares,
        )
        sym = args.symbol.upper()
        run_id = args.run_id or make_run_id(prefix="paper", symbol=sym, strategy=args.strategy)
        out_dir = runs_parent / run_id
        tick_count = 0

        def _on_tick(_tick, state) -> None:
            nonlocal tick_count
            tick_count += 1
            eq = state.cash + state.shares * _tick.price
            print(
                json.dumps(
                    {
                        "ts_event_ns": _tick.ts_event_ns,
                        "price": _tick.price,
                        "shares": state.shares,
                        "cash": round(state.cash, 2),
                        "equity": round(eq, 2),
                        "killed": state.killed,
                    }
                )
            )

        try:
            state = asyncio.run(
                run_paper_session(
                    strategy=strat,
                    symbol=sym,
                    interval=args.interval,
                    cfg=cfg,
                    max_ticks=args.max_ticks,
                    on_tick=_on_tick,
                )
            )
        except KeyboardInterrupt:
            print("interrupted — paper session stopped", file=sys.stderr)
            raise SystemExit(130) from None
        except Exception as exc:
            print(exc, file=sys.stderr)
            raise SystemExit(2) from exc

        manifest_path = write_paper_manifest(
            out_dir=out_dir,
            symbol=sym,
            interval=args.interval,
            strategy_name=args.strategy,
            model_path=str(args.model.resolve()) if args.model else None,
            cfg=cfg,
            state=state,
            tick_count=tick_count,
        )
        print("paper run:", out_dir)
        print("manifest:", manifest_path)
        if state.killed:
            print("killed:", state.kill_reason, file=sys.stderr)
        return

    if args.cmd != "replay-parquet":
        parser.error(f"unknown {args.cmd!r}")

    cfg = ReplayConfig(
        slip_bps=args.slip_bps,
        fee_per_share=args.fee_per_share,
        initial_cash=args.initial_cash,
    )
    runs_parent = _runs_parent(args.data_root)

    try:
        strat = resolve_strategy(
            args.strategy,
            target_shares=args.target_shares,
            model_path=args.model,
        )
    except ValueError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2) from exc

    ticks = filter_price_bars(parquet_to_ticks(args.ticks.resolve()))
    sym = ticks[0].symbol if ticks else "EMPTY"
    run_id = args.run_id or make_run_id(prefix="pq", symbol=sym, strategy=args.strategy)

    try:
        outcome = replay_ticks(strat, ticks, cfg)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2) from exc

    pn = summarize_pnl(cfg, outcome)
    manifest_core = {
        "cmd": args.cmd,
        "strategy": args.strategy,
        "tick_count": len(ticks),
        "fills_count": len(outcome.fills),
        "replay_config": {
            "initial_cash": cfg.initial_cash,
            "slip_bps": cfg.slip_bps,
            "fee_per_share": cfg.fee_per_share,
        },
        "pnl_summary_approx": pn,
        "final_cash": outcome.final_cash,
        "final_shares": outcome.final_shares,
        "git_sha": _git_sha_optional(),
        "runs_parent": str(runs_parent),
        "tick_file": str(args.ticks.resolve()),
    }
    if args.model is not None:
        manifest_core["model_path"] = str(args.model.resolve())

    out_dir = write_run_bundle(
        outcome=outcome,
        manifest={"run_id": run_id} | manifest_core,
        run_id=run_id,
        runs_parent=runs_parent,
    )
    print("run:", out_dir)
    print(json.dumps(pn))


if __name__ == "__main__":
    main()
