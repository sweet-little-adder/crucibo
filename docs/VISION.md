# Vision

## Thesis

**Crucibo** is systematic **trading infrastructure for US equities first**: market data → decision → risk → execution, with clocks and economics that stay honest under scrutiny.

Crypto (Binance) is an **optional** venue, not the product identity.

**Crucibo** owns data, replay, paper/live runtime, fills, fees, kill switches, order state, reconcile, and latency measurement.  
**morning-star** (separate repo) owns features, training, walk-forward, and checkpoint export.

## Outcomes

1. **Ingest** — Normalized US equity bars/ticks (Alpha Vantage primary; Polygon optional).
2. **Clock model** — Event time + ingest time; **RTH session clock** on the live equities path.
3. **Simulator** — Deterministic backtest/replay with PnL, fills, commissions, slip.
4. **Paper** — Live equity feeds, virtual fills, required kill/notional guards, `data/runs/` bundles.
5. **Live equities** — Order state machine, local account book, broker reconcile, dry-run or **Alpaca paper** signed REST.
6. **Risk** — Max loss, max position, max notional — pre-trade and mark-to-market.
7. **Latency** — Measured feed lag / decision / tick-to-order with optional hard budgets.

## Non-goals (deferred)

- Co-located competitive HFT without colo + venue economics.
- Crypto-first product positioning.
- Live money trading without explicit capital acceptance and ops design.

## Success criterion

Train → replay → paper equities → `live-equities` (dry-run or Alpaca paper) share the same decision/risk/order shape; every run is reproducible from manifest + data slice; latency is measured on the path that will carry real stock orders.
