import pytest
from pydantic import ValidationError

from crucibo.models import TradeTick


def test_trade_tick_basic() -> None:
    t = TradeTick(
        ts_event_ns=1_720_000_000_000_000_000,
        ts_ingest_ns=1_720_000_000_001_000_000,
        symbol="TEST",
        price=10.0,
        size=100,
    )
    assert t.schema_version == 1


def test_trade_tick_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        TradeTick.model_validate(
            {
                "ts_event_ns": 100,
                "symbol": "X",
                "price": 1.0,
                "size": 1,
                "ghost": True,
            }
        )
