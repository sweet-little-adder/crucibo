# Roadmap

Phases are **capabilities**, not calendar promises.

## Principles

- **Real data first** — Binance futures (free), Alpha Vantage (free), Polygon optional.
- **Event-time honesty** — no lookahead; manifests on every run.
- **morning-star trains, crucibo executes** — artifact contract between repos.
- **Paper before live** — kill switch required on any real-time loop.
- **Same path upward** — paper and live dry-run share execution/risk surfaces.

---

## Phase 1 — Ingest + schema (done)

- [x] Typed `TradeTick` / `NewsEvent` + Parquet I/O
- [x] Alpha Vantage daily + intraday
- [x] **Binance USD-M futures** klines + mark price + funding
- [x] Polygon trades (paid), RSS news (free)
- [x] Silver layout + per-slice manifests

---

## Phase 2 — Replay + strategies (done)

- [x] `replay_ticks` sorted by `ts_event_ns`
- [x] Strategies: `flat`, `buy_hold`, `neural`, **`morning_star` / `aapl_mlp_v1`**
- [x] Run bundles: fills, equity curve, manifest
- [x] CLI: `replay-parquet`, `train-from-parquet`

---

## Phase 3 — Research discipline (in progress)

- [x] **Walk-forward** in morning-star (`walk-forward` CLI)
- [x] **PyTorch trainer** in morning-star (exports numpy weights for crucibo)
- [ ] Costs model object vs loose floats in crucibo
- [ ] Session clock (RTH) for US intraday bars
- [ ] Attribution hooks in replay manifest

---

## Phase 4 — Paper on live feeds (done)

- [x] **Paper trading** — `paper-binance` / `paper-alphavantage` on live feeds
- [x] Kill switch (`--max-loss-usd`) + position/notional caps
- [x] Required safety guards (or explicit `--allow-no-kill`)
- [x] **Record paper runs under `data/runs/`** — fills, equity curve, manifest, latency
- [x] Interrupt-safe partial flush on Ctrl-C (when ticks already applied)
- [x] Dashboard SSE + show recording
- [ ] Merge `NewsEvent` + bars by event time in replay
- [ ] News-aware features in morning-star

---

## Phase 5 — Live path (in progress)

- [x] **Execution backend seam** — paper vs `live_dry_run` (`crucibo.live`)
- [x] **Dry-run broker** — order intents + ack log, no real capital
- [x] Pre-trade risk module (shared limits)
- [x] Latency tracker (feed lag, decision, tick-to-order) in manifests
- [x] CLI `--mode live_dry_run` on paper commands
- [ ] Signed live broker (Binance API keys, order state machine)
- [ ] Capital limits + kill enforced on real orders
- [ ] Position reconciliation vs exchange

---

## Phase 6 — HFT-shaped infra

- [x] Latency as measured property on paper/live-dry-run path
- [x] Hot-path seam (strategy → risk → broker → fill)
- [ ] Continuous profiling budgets on critical path
- [ ] Native acceleration only where profiler proves need
- [ ] Finer market data (ticks / L2) when venue + cost justify it
- [ ] Co-lo / competitive nanosecond claims — only with hardware + venue economics
