# Vision

## Thesis

**Crucibo** is systematic **trading infrastructure**: market data → decision → risk → execution, with clocks and economics that stay honest under scrutiny.

**Crucibo** owns data, replay, paper/live runtime, fills, fees, kill switches, and latency measurement.  
**morning-star** (separate repo) owns features, training, walk-forward, and checkpoint export.

Today the stack bootstraps from limited-scope research. The destination is **live trading** and **HFT-shaped systems** — deterministic event time, measurable latency, kill switches, capital limits, and a path from replay → paper → live dry-run → live that does not rewrite the world at each stage.

## Outcomes

1. **Ingest** — Normalized ticks/bars into partitioned, immutable archives.
2. **Clock model** — Explicit event time, ingest time, never “pretend we saw the future.”
3. **Simulator** — Deterministic backtest/replay with PnL, fills, commissions, slip.
4. **Paper** — Live feeds, virtual fills, required kill/notional guards, full run bundles under `data/runs/`.
5. **Live path** — Same execution backend surface; dry-run broker today; signed REST tomorrow.
6. **Risk** — Max loss, max position, max notional — first-class pre-trade checks.
7. **Latency** — Feed lag and decision path recorded as stats, not marketing claims.

## Non-goals (deferred engineering, not identity)

- Co-located competitive HFT without colo + venue economics.
- Full Reg NMS / borrow-locate before a simpler live path works.
- Live trading without kill switch + capital limits.

## Success criterion

Train → replay → paper on live feed → live dry-run produces the same *decision shape* on overlapping history; every run is reproducible from manifest + data slice; latency is measured on the path that will carry real orders.
