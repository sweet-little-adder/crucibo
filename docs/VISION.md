# Vision

## Thesis

**Crucibo + morning-star** is an execution and evaluation plane for systematic models: ingest real market data, train in a separate repo, replay and paper-trade with honest event-time clocks, explicit economics, and auditable manifests.

**Crucibo** owns data, replay, paper/live runtime, fills, fees, and kill switches.  
**morning-star** owns features, training, walk-forward, and checkpoint export.

Non-negotiable: no lookahead, reproducible runs, kill switches before real capital.

## Outcomes

1. **Ingest** — Normalized `TradeTick` archives (Alpha Vantage, Binance futures, optional Polygon/RSS).
2. **Model harness** — morning-star exports versioned artifacts; crucibo loads them as `TickStrategy` without importing PyTorch.
3. **Replay** — Deterministic backtest with PnL, fills, slippage, run manifests.
4. **Walk-forward** — Train window vs OOS window in morning-star before trusting a checkpoint.
5. **Paper trading** — Live Binance kline WebSocket feed, virtual fills, drawdown kill switch.
6. **Risk scaffolding** — Max position, max loss USD, explicit kill reasons in manifests.

## Near-term goals

- Richer features in morning-star (funding, mark price, news embeddings).
- Multi-stream replay (bars + news by event time).
- Live broker bridge (separate design doc, explicit capital limits).

## Non-goals (for now)

- Colocated HFT / microstructure queue simulation.
- Full Reg NMS / borrow-locate realism.
- Live trading without kill switch + max-notional caps.

## Success criterion

Train in morning-star → replay in crucibo → paper on live feed produces the same *decisions* on overlapping history, and every run is reproducible from manifest + data slice.
