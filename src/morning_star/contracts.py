"""Contract constants shared with crucibo's morning_star loader."""

from __future__ import annotations

CONTRACT_VERSION = 1
PRODUCER = "morning-star"
MODEL_TYPE_MLP_V1 = "mlp_v1"
ACTION_TARGET_SHARES = "target_shares"

MANIFEST_FILENAME = "manifest.json"
WEIGHTS_FILENAME = "weights.npz"

# Additive model types (contract_version stays 1; an old loader rejects unknown types loudly).
MODEL_TYPE_LINEAR_V1 = "linear_v1"
MODEL_TYPE_TREES_V1 = "trees_v1"
# Indices into feature schema v1 (ret_1, mean_ret, price_z, position_norm, cash_norm) that the
# linear_v1 / trees_v1 models read. position_norm and cash_norm are runtime state, never inputs.
MARKET_FEATURE_INDICES = (0, 1, 2)
