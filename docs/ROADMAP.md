# Roadmap

Phases are **capabilities**, not calendar promises. Revisit when ingest, replay, or live assumptions change.

## Principles

- **Real data first** — Alpha Vantage free tier for daily/intraday bars; Polygon optional for ticks; more venues as needed.
- **Event-time honesty** — no lookahead; manifests on every run.
- **Kill bad ideas cheaply** — replay with fees → paper with kill switch → live with capital limits.
- **Same path upward** — research is how we *earn* live; it is not a permanent identity of “not trading infra.”

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

## Phase 4 — Paper on live feeds (next)

- [ ] Paper-trading loop on a live market data feed (poll or WebSocket)
- [ ] Explicit kill switch + max loss / max position
- [ ] Record paper runs under `data/runs/` (equity snapshots, kill reason)
- [ ] Merge `NewsEvent` + bars by event time in replay (optional parallel track)

---

## Phase 5 — Live trading

- [ ] Broker bridge (order state machine, auth, reconnect, client order IDs)
- [ ] Capital limits + kill switch enforced on the live path (same vocabulary as paper)
- [ ] Reconciliation: intended position vs exchange position
- [ ] Separate design doc before real capital (risk, ops, failure modes)

---

## Phase 6 — HFT-shaped infra

- [ ] Latency budgets on critical path; continuous profiling
- [ ] Hot-path isolation (strategy decision vs I/O vs risk)
- [ ] Native acceleration only where profiler proves need (see [STACK.md](STACK.md))
- [ ] Finer market data (ticks / L2) when venue + cost justify it
- [ ] Co-lo / competitive nanosecond claims — only with hardware + venue economics; not a README flex
