#!/usr/bin/env bash
# Run MA crossover backtest on ingested AAPL daily bars.
set -euo pipefail

SYMBOL="${SYMBOL:-AAPL}"
INTERVAL="${INTERVAL:-daily}"
START="${START:-2026-02-11}"
END="${END:-2026-06-01}"

crucibo backtest \
  --strategy ma_crossover \
  --symbol "$SYMBOL" \
  --interval "$INTERVAL" \
  --fast 12 \
  --slow 26 \
  --start "$START" \
  --end "$END"