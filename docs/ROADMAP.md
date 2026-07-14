# Roadmap

Phases are **capabilities**, not calendar promises.

## Principles

- **US equities first** — Alpha Vantage (free) + optional Polygon ticks; Alpaca paper for signed orders.
- **Crypto optional** — Binance USD-M paper/ingest is supported but not the primary path.
- **Event-time honesty** — no lookahead; manifests on every run.
- **Paper before live** — kill switch required on any real-time loop.
- **Same path upward** — paper, dry-run, and live equities share risk/order/recon surfaces.

---

## Phase 1 — Ingest + schema (done)

- [x] Typed `TradeTick` / `NewsEvent` + Parquet I/O
- [x] Alpha Vantage daily + intraday (**primary**)
- [x] Polygon trades (paid, optional)
- [x] Binance USD-M futures klines (optional crypto)
- [x] RSS news (free)
- [x] Silver layout + per-slice manifests

---

## Phase 2 — Replay + strategies (done)

- [x] `replay_ticks` sorted by `ts_event_ns`
- [x] Strategies: `flat`, `buy_hold`, `neural`, `aapl_mlp_v1`
- [x] Run bundles: fills, equity curve, manifest
- [x] CLI: `replay-parquet`, `train-from-parquet`, v2 `ingest` / `backtest` / `report`

---

## Phase 3 — Research discipline (in progress)

- [x] Walk-forward in morning-star
- [x] PyTorch trainer export for crucibo
- [ ] Costs model object vs loose floats in crucibo
- [x] Session clock (RTH) for US equities live path
- [ ] Attribution hooks in replay manifest

---

## Phase 4 — Paper on live feeds (done)

- [x] Paper trading — `paper-alphavantage` (stocks) + optional `paper-binance`
- [x] Kill switch + position/notional caps + required safety guards
- [x] Record under `data/runs/` (fills, equity, latency)
- [x] Interrupt-safe partial flush
- [x] Dashboard SSE + show recording

---

## Phase 5 — Live equities path (done for Aim foundation)

- [x] **`live-equities` CLI** — stocks-first primary live command
- [x] Execution backend seam (paper / live_dry_run / live equities runtime)
- [x] Order state machine (`OrderBook` / phases)
- [x] Local account book + **broker reconcile**
- [x] Dry-run equity broker (default, no keys)
- [x] **Alpaca paper** signed REST broker (optional keys)
- [x] Capital limits + kill enforced on live path
- [x] Flatten-on-kill
- [x] Latency budgets (warn / optional enforce)
- [ ] Alpaca **live money** endpoint (requires explicit ops design + funding)
- [ ] Multi-symbol portfolio live loop

---

## Phase 6 — HFT-shaped infra

- [x] Latency as measured property (feed lag, decision, tick-to-order)
- [x] Hot-path seam: strategy → risk → order SM → broker → recon
- [x] Configurable latency budgets on critical path
- [ ] Continuous profiling dashboards / CI budgets
- [ ] Native acceleration only where profiler proves need
- [ ] L2 / tick hot path when venue + cost justify it
- [ ] Co-lo claims only with hardware + venue economics
