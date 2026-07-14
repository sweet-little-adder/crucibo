#!/usr/bin/env bash
# US equities ingest example (Alpha Vantage free tier — requires API key in .env)
set -euo pipefail
cd "$(dirname "$0")/.."
set -a && source .env && set +a
.venv/bin/crucibo ingest --symbol AAPL --interval daily