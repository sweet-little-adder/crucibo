# Glossary

Terms used across crucibo docs. Definitions are **pedagogical**, not legal or exchange-official.

| Term | Short meaning |
|------|----------------|
| **Event time** | Timestamp assigned by the tape / exchange for when something happened |
| **Ingest time** | When your system recorded or received an event |
| **Lookahead bias** | Accidentally using information not knowable at simulated decision time |
| **Replay** | Feeding historical events through the same logic path with a simulated clock |
| **Slippage** | Difference between intended price and realized fill (model or empirical) |
| **NBBO** | National Best Bid and Offer (US equities consolidated top-of-book) |
| **MM** | Market maker—posts liquidity, earns spread / rebates, takes inventory risk |
| **Prop shop** | Firm trading its own capital; structure varies widely |
| **Bar** | OHLCV bucket over a time window |
| **Tick** | Trade (or quote—be precise in your schema) event |
| **Manifest** | Run metadata: data hashes, git SHA, config hash, versions |
| **Partition** | Directory or file split by date/symbol for scalable IO |
| **Attribution** | Breaking PnL into drivers (fees, drift, vol, luck) |

Add new rows as jargon appears in code reviews with yourself.
