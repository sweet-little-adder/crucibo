# Walk-forward model comparison

Exploratory research harness. It does not claim a tradeable edge. Config is frozen in
`configs/compare_v2.json` (hash is recorded in every results file); thresholds are fixed, nothing is
selected on test data.

## Run

```bash
pip install -e ".[dev,compare]"
python scripts/fetch_yahoo_daily.py          # writes data/ (gitignored)
morning-star compare --config configs/compare_v2.json --data-dir data --out results_compare.json
```

## Data and redistribution

`scripts/fetch_yahoo_daily.py` pulls daily OHLCV from Yahoo's unofficial chart endpoint and scales
O/H/L/C by adjclose/close (split + dividend adjusted, total-return basis; features, fills and
buy&hold share that basis). Yahoo data is not a licensed redistributable source, so market data is
never committed (`data/` is gitignored). Only the fetch code, SHA-256 of the raw responses and fetch
time (`data/PROVENANCE.json`) are kept. Any other daily-bar source with `date,o,h,l,c,v` works.

## Protocol

Yearly expanding walk-forward; training rows are purged so their 5-bar label window ends before the
test year starts; scalers fit on training rows only; signal at close t, fill at open t+1, positions
continuous across folds; entry and terminal exit costs; sizing convention below; drawdown from the starting equity;
6 bps per side by default (crucibo EconomicsConfig: 4 fee + 2 slippage). AUC and excess-return
intervals are moving-block bootstrap intervals (descriptive, not a significance test).

## Sizing and execution convention (one convention, used by the harness and by crucibo)

The decision is made at the close of bar t. On entry, shares = cash / close[t] (what a trader can
size when the signal fires), the order fills at open[t+1], and the buy is clamped to available cash
if the open gaps up. If the open gaps down, the unspent cash stays idle. Shares are held, not
rebalanced, until the signal turns flat. Total cost per side is split 2/3 fee on gross and 1/3
slippage on price (6 bps = fee 4 + slip 2). Crucibo equivalent: `ArtifactModelStrategy(sizing="equity")`,
`run_backtest(latency_bars=1)`, `EconomicsConfig(clamp_buys_to_cash=True)`. Buy and hold uses the same
rule, so it is charged the same entry and exit.

## Artifact model types (contract_version 1, additive)

| model_type | Source | Notes |
|---|---|---|
| `mlp_v1` | existing | unchanged; `mlp_v2` (standardised MLP) exports as this with the scaler folded into layer 1 and zero weights on position_norm / cash_norm |
| `linear_v1` | logistic (`sigmoid`) or linear regression (`identity`, threshold 0) | stores train-only mean/std, weights, bias |
| `trees_v1` | XGBoost `binary:logistic` gbtree | tree arrays; evaluator has no xgboost dependency |

`linear_v1` and `trees_v1` read only the market features `ret_1, mean_ret, price_z`
(`feature_indices` in the manifest); position and cash never enter the model. Old v1 loaders reject
the new types with an explicit "unsupported model_type" error. Existing checkpoints are untouched.
