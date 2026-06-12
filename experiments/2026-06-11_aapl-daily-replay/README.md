# AAPL daily replay — 2026-06-11

**Goal:** First replay on real Alpha Vantage daily bars (not generated data).

## Commands

```bash
set -a && source .env && set +a
crucibo alphavantage-daily --symbol AAPL
crucibo replay-parquet \
  --ticks data/silver/alphavantage/symbol=AAPL/interval=daily/bars.parquet \
  --strategy buy_hold \
  --target-shares 100 \
  --fee-per-share 0 \
  --slip-bps 5 \
  --run-id aapl-daily-buyhold
```

## Result

- **100 daily bars** ingested (1 Alpha Vantage API call)
- **buy_hold 100 shares:** ~+$4,893 over window (AAPL ~$247 → ~$296)
- Run bundle: `data/runs/aapl-daily-buyhold/`

## Next

Walk-forward: train on first 70 bars, OOS replay on last 30.
