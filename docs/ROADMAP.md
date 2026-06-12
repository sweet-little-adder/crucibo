# Roadmap

Phases are **capabilities**, not calendar promises. Revisit when ingest or replay assumptions change.

## Principles

- **Real data first** — Alpha Vantage free tier for daily/intraday bars; Polygon optional for ticks.
- **Event-time honesty** — no lookahead; manifests on every run.
- **Kill bad ideas cheaply** — replay with fees before paper/live.

---

## Phase 1 — Ingest + schema (done)

- [x] Typed `TradeTick` / `NewsEvent` schemas + Parquet I/O
- [x] **Alpha Vantage** daily + intraday bar ingest
- [x] Polygon trades ingest (paid entitlement)
- [x] RSS news ingest (free)
- [x] Silver layout + per-slice manifests

---

## Phase 2 — Replay + naive strategy (done)

- [x] `replay_ticks` sorted by `ts_event_ns`
- [x] Strategies: `flat`, `buy_hold`, `neural` (MLP checkpoint)
- [x] Run bundles: fills, equity curve, manifest
- [x] **CLI**: `replay-parquet`, `train-from-parquet`

---

## Phase 3 — Research discipline (in progress)

- [ ] **Walk-forward CLI** — train date range vs OOS date range on same parquet
- [ ] Costs model object vs loose floats
- [ ] Session clock (RTH) for intraday bars
- [ ] Attribution hooks in manifest

---

## Phase 4 — Multi-stream (future)

- [ ] Merge `NewsEvent` + bars by event time in replay
- [ ] News-aware features (time since last headline)
- [ ] Paper-trading bridge (explicit kill switch)

---

## Phase 5 — Live (non-goals until Phase 3 boring)

- Live execution, borrow/locate, Reg NMS realism — separate explicit design.
