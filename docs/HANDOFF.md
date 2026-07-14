# Handoff sheet (read after this Cursor chat)

This file exists so **you do not rely on AI memory**.

## Where you are — 2026-06 snapshot

You are building **truthful ingest → replay → paper → live equities** (`crucibo`) — stocks-first trading infrastructure. Crypto/Binance is optional.

| Area | Status |
|------|--------|
| **Docs** (`docs/VISION.md` … ) | US equities first; live + HFT-shaped aim |
| **Alpha Vantage ingest** | **Works on free tier** — daily + intraday bars → Parquet |
| **Replay + naive fills** | **Works on real bars** (`crucibo replay-parquet`) |
| **Live equities** | **`crucibo live-equities`** — dry-run or Alpaca paper, order SM, recon, RTH |
| **Polygon ingest** | Code exists; **`/v3/trades` requires paid plan** (403 on free key) |
| **Binance (optional)** | Futures ingest + `paper-binance` — not the primary path |
| **RSS news ingest** | Free headlines → Parquet (parallel stream, not wired to replay yet) |

## Paths on disk (`CRUCIBO_DATA_ROOT`, default `./data`)

| Artefact | Path pattern |
|-----------|---------------|
| Alpha Vantage daily | `data/silver/alphavantage/symbol=TICK/interval=daily/bars.parquet` |
| Alpha Vantage intraday | `data/silver/alphavantage/symbol=TICK/interval=5min/latest/bars.parquet` |
| Polygon silver (paid) | `data/silver/polygon/symbol=TICK/date=DAY/trades.parquet` |
| Run bundle (replay) | `data/runs/<run_id>/{sim_fills.parquet,equity_curve.parquet,run_manifest.json}` |

Secrets live in **`.env` (gitignored)** — `ALPHA_VANTAGE_API_KEY`, optional `POLYGON_API_KEY`, optional `ALPACA_API_KEY` / `ALPACA_API_SECRET` for `live-equities --broker alpaca_paper`.

### Live equities (primary runtime path)

```bash
# Local dry-run broker (no Alpaca keys) — still full order SM + recon + run bundle
.venv/bin/crucibo live-equities --symbol AAPL --interval 5min \
  --strategy buy_hold --target-shares 10 \
  --max-loss-usd 500 --max-notional-usd 5000 \
  --broker dry_run --max-ticks 3

# Signed Alpaca paper (paper capital, not live money)
# set ALPACA_API_KEY + ALPACA_API_SECRET in .env
.venv/bin/crucibo live-equities --symbol AAPL --interval 5min \
  --strategy buy_hold --target-shares 10 \
  --max-loss-usd 500 --broker alpaca_paper --max-ticks 3
```

Outputs: `data/runs/live_eq_*/` with fills, equity curve, `order_book.json`, latency budgets.

---

## Primary workflow (Alpha Vantage — free)

```bash
cd ~/+/sauletrust/crucibo
python3 -m venv .venv              # once
.venv/bin/pip install -e ".[dev]" # once after pulls
cp .env.example .env               # add ALPHA_VANTAGE_API_KEY
set -a && source .env && set +a
```

### Ingest ~100 daily bars (1 API call)

```bash
.venv/bin/crucibo alphavantage-daily --symbol AAPL
```

### Replay on real data

```bash
.venv/bin/crucibo replay-parquet \
  --ticks data/silver/alphavantage/symbol=AAPL/interval=daily/bars.parquet \
  --strategy buy_hold \
  --target-shares 100 \
  --fee-per-share 0 \
  --slip-bps 5
```

Variants:

- **`--strategy flat`** — zero trades sanity check
- Tune economics: **`--slip-bps`** **`--fee-per-share`** **`--initial-cash`**

### Train MLP on real bars

```bash
.venv/bin/crucibo train-from-parquet \
  --ticks data/silver/alphavantage/symbol=AAPL/interval=daily/bars.parquet \
  --out models/aapl-daily.npz \
  --lookback 20 --forward-horizon 5 --threshold 0.55
```

**Walk-forward:** train on first ~70 bars, replay OOS on last ~30 (split parquet by date — harness TBD).

### Quality gate

```bash
.venv/bin/pytest && .venv/bin/ruff check src tests
```

---

## Paid Polygon checklist (optional — tick data)

1. Confirm plan includes **historical stock trades** (`/v3/trades`).
2. Add `POLYGON_API_KEY` to `.env`, then:

   ```bash
   .venv/bin/crucibo polygon-trades --symbol AAPL --date YYYY-MM-DD
   .venv/bin/crucibo replay-parquet --ticks data/silver/polygon/.../trades.parquet --strategy flat
   ```

---

## What to build next (`docs/ROADMAP.md`)

1. **Walk-forward CLI** — train/OOS date split on Alpha Vantage parquet.
2. **Session clock** filtering (NYSE RTH) before trusting intraday narratives.
3. **News + replay merge** — only headlines with `ts_event_ns ≤ bar time`.

---

## Continuity tips

- Record experiments under `experiments/` with exact command + data slice.
- Stamp runs: `export CRUCIBO_GIT_SHA=$(git rev-parse HEAD)` before important replays.
- Alpha Vantage free tier: **25 requests/day** — replay/train locally without spending calls.
