# morning-star

Train causal models and export versioned artifacts for **crucibo** replay and paper trading.

| Repo | Role |
|------|------|
| **morning-star** | Features, training, walk-forward, PyTorch (optional), export |
| **crucibo** | Ingest, replay, paper/live runtime, PnL, manifests |

## Install

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
# optional PyTorch trainer:
.venv/bin/pip install -e ".[dev,torch]"
```

## Commands

### Train (numpy or PyTorch)

```bash
morning-star train \
  --config configs/btc_5m_baseline.yaml \
  --ticks ../crucibo/data/silver/binance/.../bars.parquet \
  --out artifacts/btc-baseline

morning-star train --backend torch --ticks ... --out artifacts/btc-torch
```

### Walk-forward (train / OOS split)

```bash
morning-star walk-forward \
  --ticks ../crucibo/data/silver/binance/.../bars.parquet \
  --train-end 2024-06-01 \
  --oos-start 2024-06-02 \
  --out artifacts/btc-wf
```

Writes `manifest.json`, `weights.npz`, and `walk_forward_report.json`.

### Replay in crucibo

```bash
cd ../crucibo
crucibo replay-parquet \
  --ticks data/silver/binance/.../bars.parquet \
  --strategy morning_star \
  --model ../morning-star/artifacts/btc-wf
```

### Paper trade (crucibo)

```bash
crucibo paper-binance \
  --symbol BTCUSDT --interval 5m \
  --strategy morning_star \
  --model ../morning-star/artifacts/btc-wf \
  --max-loss-usd 5000 --max-ticks 3
```

## Artifact contract (v1)

```
artifacts/<run>/
  manifest.json      # contract_version, feature schema, hyperparams, walk_forward summary
  weights.npz        # numpy MLP weights (even when trained with PyTorch)
```

crucibo never imports PyTorch — only reads this bundle.

## Layout

```
src/morning_star/
  features/     causal feature builder (schema v1)
  models/       baseline numpy MLP
  train/        dataset, numpy + torch trainers, walk-forward
  eval/         OOS replay scoring
  export/       artifact writer
```
