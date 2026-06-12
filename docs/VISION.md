# Vision

## Thesis

Build **professional systematic habits**—the shape of infrastructure—on a pipeline that stays **truthful under scrutiny**, even when scope and capital assumptions are intentionally limited.

**Crucibo** is a research sandbox: fewer symbols, shorter windows, simplified economics—but **non-negotiable correctness** around time, leakage, fills, fees, and auditability.

## Outcomes

Within 6–18 months of part-time development:

1. **Ingest**: Normalized ticks or bars from a vendor into **partitioned**, **immutable** archives (dates + symbols).
2. **Clock model**: Explicit policy for **event time**, **replay lag**, optional **latency shock** knobs—never “pretend we saw the future.”
3. **Simulator**: Deterministic **backtest / replay** producing **PnL curves, fills, commissions, slip model**, parameterized by YAML/TOML.
4. **Attribution**: Explain *why* a run won or lost (turnover, spread, regimes, outliers)—with measurable drivers, not narrative guesswork.
5. **Risk scaffolding**: Caps, gross exposure placeholders, sanity checks—even if simplistic at first.

## Non-goals

- Competitive HFT latency.
- Borrow, locate, full Reg NMS order-routing realism on day one.
- Live trading without a separate, explicit “kill switch + capital limit” design (even paper).

## Reproducibility

- Each run writes a **manifest**: data slice reference, git commit, config, and environment metadata where available.
- Simulation errors should surface explicitly rather than producing silently wrong PnL.

## US equities scope (default)

Single exchange tape or consolidated **vendor abstraction** behind one interface (`DATA.md`). Start **one mega-cap**, expand only when ingestion is autopilot.

## Success criterion

If you cannot **reproduce** last month’s experiment on Tuesday, it did not happen.
