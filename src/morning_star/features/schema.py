"""Versioned feature schema — must stay aligned with crucibo.features."""

from __future__ import annotations

FEATURE_SCHEMA_VERSION = 1
FEATURE_NAMES = ("ret_1", "mean_ret", "price_z", "position_norm", "cash_norm")
FEATURE_DIM = len(FEATURE_NAMES)
