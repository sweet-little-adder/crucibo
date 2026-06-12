"""Environment-backed knobs (secrets stay out of git)."""

from __future__ import annotations

import os


def polygon_api_key() -> str:
    key = os.environ.get("POLYGON_API_KEY", "").strip()
    if not key:
        msg = (
            "Missing POLYGON_API_KEY. Copy .env.example → .env and export the key "
            "(or `export POLYGON_API_KEY=...` in your shell)."
        )
        raise RuntimeError(msg)
    return key


def alpha_vantage_api_key() -> str:
    key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    if not key:
        msg = (
            "Missing ALPHA_VANTAGE_API_KEY. Get a free key at "
            "https://www.alphavantage.co/support/#api-key then add to .env "
            "(or `export ALPHA_VANTAGE_API_KEY=...` in your shell)."
        )
        raise RuntimeError(msg)
    return key
