# morning-star

Train causal bar/tick models and export versioned artifacts for **crucibo** replay.

crucibo owns ingest, replay, fills, and PnL. morning-star owns features, training, and checkpoints. They meet at Parquet in and artifact bundle out — crucibo never imports this package.

## Install

```bash
cd morning-star
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

## Train (baseline MLP)

```bash
# ingest first (from crucibo)
cd ../crucibo
.venv/bin/crucibo ingest-binance --symbol BTCUSDT --interval 5m --start-date 2024-01-01

# train + export
cd ../morning-star
.venv/bin/morning-star train \
  --ticks ../crucibo/data/silver/binance/symbol=BTCUSDT/interval=5m/start=2024-01-01/end=latest/bars.parquet \
  --out artifacts/btc-5m-baseline

# replay in crucibo
cd ../crucibo
.venv/bin/crucibo replay-parquet \
  --ticks data/silver/binance/symbol=BTCUSDT/interval=5m/start=2024-01-01/end=latest/bars.parquet \
  --strategy morning_star \
  --model ../morning-star/artifacts/btc-5m-baseline
```

## Artifact bundle

Each run writes a directory:

```
artifacts/<name>/
  manifest.json   # contract metadata (source of truth)
  weights.npz     # numpy MLP weights
```

`contract_version` and `feature_schema_version` must match what crucibo's loader expects.

## Layout

```
src/morning_star/
  features/     causal feature builder (schema versioned)
  models/       baseline MLP
  train/        dataset + training loop
  export/       manifest + weights writer
```
