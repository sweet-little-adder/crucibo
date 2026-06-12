# Named model checkpoints

Pre-trained MLP strategy weights for `--strategy neural` in replay.

> **Note:** These checkpoints were trained before the Alpha Vantage migration. Retrain on real bars with `train-from-parquet` for production research.

## Dawnbreaker (`models/dawnbreaker.npz`)

Conservative profile — longer lookback, higher threshold, smaller size.

| Field | Value |
|-------|-------|
| **Replay** | `crucibo replay-parquet --strategy neural --model models/dawnbreaker.npz --ticks <bars.parquet>` |

## Duskbringer (`models/duskbringer.npz`)

Aggressive profile — shorter horizon, lower threshold, larger size.

| Field | Value |
|-------|-------|
| **Replay** | `crucibo replay-parquet --strategy neural --model models/duskbringer.npz --ticks <bars.parquet>` |

---

## Retrain on real Alpha Vantage data

```bash
set -a && source .env && set +a
crucibo alphavantage-daily --symbol AAPL

crucibo train-from-parquet \
  --ticks data/silver/alphavantage/symbol=AAPL/interval=daily/bars.parquet \
  --out models/aapl-daily.npz \
  --lookback 30 --forward-horizon 5 --threshold 0.55 --target-shares 30

crucibo replay-parquet \
  --ticks data/silver/alphavantage/symbol=AAPL/interval=daily/bars.parquet \
  --strategy neural \
  --model models/aapl-daily.npz
```

Checkpoints are `.npz` (NumPy) with weights + hyperparameters JSON sidecar inside the archive.
