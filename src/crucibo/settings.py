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


def alpaca_credentials() -> tuple[str, str]:
    """Alpaca API key + secret for US equities paper/live trading."""

    key = os.environ.get("ALPACA_API_KEY", "").strip() or os.environ.get(
        "APCA_API_KEY_ID", ""
    ).strip()
    secret = os.environ.get("ALPACA_API_SECRET", "").strip() or os.environ.get(
        "APCA_API_SECRET_KEY", ""
    ).strip()
    if not key or not secret:
        raise RuntimeError(
            "Missing ALPACA_API_KEY / ALPACA_API_SECRET (or APCA_API_KEY_ID / "
            "APCA_API_SECRET_KEY). Create a free paper key at https://alpaca.markets "
            "and add them to .env."
        )
    return key, secret
