# Vision

## Thesis

**Crucibo** is systematic **trading infrastructure**: market data → decision → risk → execution, with clocks and economics that stay honest under scrutiny.

Today the stack looks like a research sandbox (limited symbols, simplified fills). That is the **boot path**, not the ceiling. The destination is **live trading** and **HFT-shaped systems** — deterministic event time, measurable latency, kill switches, capital limits, and a path from replay → paper → live that does not rewrite the world at each stage.

## Outcomes

1. **Ingest** — Normalized ticks/bars into partitioned, immutable archives (dates + symbols + venue).
2. **Clock model** — Explicit **event time**, replay lag, optional latency shock — never “pretend we saw the future.”
3. **Simulator** — Deterministic backtest/replay with PnL, fills, commissions, slip models, parameterized config.
4. **Attribution** — Why a run won or lost (turnover, spread, regimes, outliers) with measurable drivers.
5. **Risk** — Caps, gross exposure, drawdown kill switches — required before real capital.
6. **Live path** — Same strategy contract on paper and live: virtual fills first, then broker bridge with explicit max notional and kill reasons in every manifest.
7. **HFT-shaped infra** — Hot-path discipline (profile before rewrite), low-latency market data and order loops where it matters, native code only when Python is proven the bottleneck — **latency as engineering**, not a vibe.

## Near-term goals

- Paper trading on live feeds (WebSocket/poll) with session recording and kill switch.
- Live broker integration (order state machine, reconnection, idempotent client order IDs).
- Latency budgets and profiling on the critical path (ingest → signal → risk → order).
- Multi-stream event time (bars + trades + news) without lookahead.

## Explicit non-goals (for now)

These are **deferred engineering**, not identity:

- **Co-located competitive HFT** — beating prop shops on nanoseconds requires colo, FPGA, exchange co-location economics. We build *toward* that discipline; we do not claim it on day one.
- Full Reg NMS / borrow-locate / smart order routing realism before a simpler live path works.
- Marketing claims of market edge from backtests alone.

## Reproducibility

- Each run writes a **manifest**: data slice, git commit, config, environment metadata.
- Simulation and live errors surface explicitly rather than silently wrong PnL.
- Paper and live share the same risk/kill vocabulary so production is not a different religion.

## Default market scope

Start with vendors and venues you can actually operate (US equities bars; expand to futures/crypto venues as ingest is autopilot). One liquid symbol until the pipeline is boring; then scale.

## Success criterion

If you cannot **reproduce** last month’s experiment on Tuesday, it did not happen.  
If paper and live diverge on the same signal path without a logged reason, the infra is lying.
