#!/usr/bin/env bash
# Print full metrics and equity chart for the latest backtest run.
set -euo pipefail

RUN_ID="${RUN_ID:-latest}"
OUTPUT="${OUTPUT:-examples/results}"

crucibo report --run-id "$RUN_ID" --output "$OUTPUT"