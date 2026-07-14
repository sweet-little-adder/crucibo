"""Trading cost models for the simulation broker."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EconomicsConfig:
    """US equities / crypto-agnostic bps fee model."""

    initial_cash: float = 1_000_000.0
    fee_bps: float = 4.0
    slippage_bps: float = 2.0
    latency_bars: int = 0
    max_position_shares: int | None = None

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be > 0")
        if self.fee_bps < 0 or self.slippage_bps < 0:
            raise ValueError("fee_bps and slippage_bps must be >= 0")
        if self.latency_bars not in (0, 1):
            raise ValueError("latency_bars must be 0 (fill at signal bar) or 1 (next bar open)")


def slip_multiplier(*, side: str, slip_bps: float) -> float:
    m = slip_bps / 10_000.0
    if side == "BUY":
        return 1.0 + m
    return 1.0 - m


def fee_cash(*, notional: float, fee_bps: float) -> float:
    return abs(notional) * (fee_bps / 10_000.0)