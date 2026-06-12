# Data (US equities)

## Principles

1. **Vendor boundary**: Normalize through small adapters (e.g. `crucibo.polygon`).
2. **Immutable slices**: Prefer **append-only partitions** `(date=YYYY-MM-DD)(symbol=AAPL.parquet)` or hive-style dirs.
3. **Schema versioning**: `schema_version` in metadata; bump when columns change.

## Minimal schema (starter targets)

### Tick (illustrative)

| Field | Type | Notes |
|-------|------|-------|
| `ts_event` | ns UTC | Exchange or vendor event timestamp |
| `ts_ingest` | ns UTC | When you received/stored (optional but powerful) |
| `symbol` | str | Canonical symbol |
| `price` | f64 | Last trade or mid policy (document which) |
| `size` | i64 | Shares |
| `conditions` | str or list | Vendor flags if available |

### Bar (1m example)

| Field | Type |
|-------|------|
| `ts_open` | ns UTC |
| `open`, `high`, `low`, `close` | f64 |
| `volume` | i64 |

## Vendors (examples—verify pricing & ToS yourself)

| Kind | Examples | Notes |
|------|----------|-------|
| Retail-friendly APIs | Polygon, Tiingo, Nasdaq Data Link | Good for **learning**; tick history can get expensive fast |
| Higher-fidelity / pro-ish | Databento, vendors via exchange | Better **tape hygiene**; still not colo |

**Rule**: cap monthly spend; start **one symbol × one week** of ticks or **one year** of daily until pipelines are boring.

## Polygon (implemented)

- **Auth**: shell env `POLYGON_API_KEY` (never commit — see [.env.example](.env.example)).
- **CLI**: `crucibo polygon-trades --symbol AAPL --date 2025-06-03`
- **API**: `GET /v3/trades/{ticker}` with `timestamp.gte` / `timestamp.lte` set to the same **UTC calendar** `YYYY-MM-DD` ([docs](https://polygon.io/docs/stocks/getting-started)).
- **Mapping**: `participant_timestamp` (ns) → `ts_event_ns`; ingest wall clock → `ts_ingest_ns` (same nanosecond batch for each HTTP pull); Polygon `conditions` list → comma-separated string.
- **Output**: `data/silver/polygon/symbol=TICKER/date=YYYY-MM-DD/trades.parquet` + `manifest.json` (row count, SHA-256, fetch time). Override parent with env `CRUCIBO_DATA_ROOT`.
- **Tiers**: **`/v3/trades` historical ticks often require a paid “trades/ticks” capable Stocks plan.** `403 Forbidden` usually means “key OK, entitlement not”; read the JSON `message` in the error—we now surface it from the CLI. `401` = bad/missing key.
- **Alternative**: use **Alpha Vantage** daily bars (free) for swing/daily research before paying for ticks.
- **Caveat**: a “US trading day” is not always aligned to **UTC midnight** slicing; start with experiments where session boundaries match your hypothesis, then refine session filters in Phase 2.

## Alpha Vantage (implemented — free tier)

- **Auth**: `ALPHA_VANTAGE_API_KEY` in `.env` — free key at [alphavantage.co/support/#api-key](https://www.alphavantage.co/support/#api-key).
- **Limits**: **25 API requests/day**, **5/minute** on free tier. Each ingest command = **1 request**.
- **CLI**:
  - `crucibo alphavantage-daily --symbol AAPL` — ~100 **daily** bars (best bang per request for OOS splits)
  - `crucibo alphavantage-intraday --symbol AAPL --interval 5min` — ~100 **intraday** bars (recent session window)
- **Mapping**: each OHLCV bar → one `TradeTick` at **bar close** with `conditions=alphavantage:daily` or `alphavantage:intraday-5min`.
- **Output**:
  - Daily: `data/silver/alphavantage/symbol=AAPL/interval=daily/bars.parquet`
  - Intraday: `data/silver/alphavantage/symbol=AAPL/interval=5min/latest/bars.parquet`
- **Not tick data**: bar granularity (1 day or 5 min). Good for swing/daily research and walk-forward; not microstructure.
- **Delay**: free-tier US intraday is **~15-minute delayed** (fine for backtest, not for live scalping).
- **Replay**: same as Polygon silver — `crucibo replay-parquet --ticks …/bars.parquet`

## Storage layout (proposed)

```
data/
  silver/polygon/symbol=AAPL/date=2025-06-03/   # parquet + manifest (crucibo default)
  silver/alphavantage/symbol=AAPL/interval=daily/bars.parquet
  silver/news/source=fed-press/date=2026-06-11/ # articles.parquet + manifest.json
  raw/       # optional future: vendor blobs
```

## News (RSS — implemented)

Free headline ingest for macro / market context. **No API key required.**

- **CLI**: `crucibo rss-feeds` — list curated feeds; `crucibo rss-ingest --source fed-press --date 2026-06-11`; `crucibo rss-ingest --all --date 2026-06-11`
- **Curated feeds**: Federal Reserve press, SEC press releases, BBC business, MarketWatch top stories (see `crucibo.news.feeds`).
- **Custom feed**: `crucibo rss-ingest --feed-url https://… --source my-feed --date 2026-06-11`
- **Mapping**: RSS/Atom `published` / `updated` → `ts_event_ns`; batch wall clock → `ts_ingest_ns`; `guid` or `link` for dedup.
- **Output**: `data/silver/news/source=SOURCE/date=YYYY-MM-DD/articles.parquet` + `manifest.json`.
- **Day filter**: UTC calendar day of `ts_event_ns` (not exchange session boundaries).
- **ToS**: Public RSS is free to fetch for personal research; **you** are responsible for redistribution/display rules per publisher.
- **Replay integration**: not wired yet — news is a parallel silver stream for future multi-source replay / feature enrichment.

### NewsEvent schema (v1)

| Field | Type | Notes |
|-------|------|-------|
| `ts_event_ns` | i64 | Published or updated time (UTC ns) |
| `ts_ingest_ns` | i64 optional | When crucibo stored the row |
| `source` | str | Feed id (`fed-press`, …) |
| `guid` | str | Dedup key |
| `url` | str | Canonical link |
| `title` | str | Headline |
| `summary` | str optional | Snippet / description |
| `author` | str optional | Feed author if present |
| `symbols` | str optional | Comma-separated tickers (future enrichment) |

## Legal / compliance note

You are responsible for **license terms**, **redistribution**, and **display** rules. This repo stores **no** third-party data by default.
