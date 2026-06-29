# Roadmap

Phases are **capabilities**, not calendar promises.

## Principles

- **Real data first** — Binance futures (free), Alpha Vantage (free), Polygon optional.
- **Event-time honesty** — no lookahead; manifests on every run.
- **morning-star trains, crucibo executes** — artifact contract between repos.
- **Paper before live** — kill switch required on any real-time loop.

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
- [x] Strategies: `flat`, `buy_hold`, `neural`, **`morning_star`**
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

## Phase 4 — Multi-stream + paper (in progress)

- [x] **Paper trading** — `paper-binance` on live kline WebSocket (virtual fills)
- [ ] Merge `NewsEvent` + bars by event time in replay
- [ ] News-aware features in morning-star
- [ ] Record paper runs under `data/runs/` with equity snapshots

---

## Phase 5 — Live (future)

- Live broker integration (Binance API keys, order state machine)
- Borrow/locate, Reg NMS — separate explicit design
- Latency profiling before any “HFT” claims
