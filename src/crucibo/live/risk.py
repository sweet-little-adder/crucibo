"""Pre-trade risk checks — shared by paper and live paths."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskLimits:
    max_loss_usd: float | None = None
    max_position_shares: int | None = None
    max_notional_usd: float | None = None
    require_kill: bool = True


@dataclass(frozen=True)
class RiskVerdict:
    ok: bool
    reason: str | None = None
    clamped_target: int | None = None


def check_pretrade(
    *,
    target_shares: int,
    position: int,
    cash: float,
    mark_price: float,
    equity: float,
    equity_peak: float,
    limits: RiskLimits,
) -> RiskVerdict:
    """Return whether an intended rebalance is allowed; may clamp target."""

    if target_shares < 0:
        return RiskVerdict(ok=False, reason="short selling not supported")

    want = target_shares
    if limits.max_position_shares is not None:
        want = min(want, limits.max_position_shares)
    if limits.max_notional_usd is not None and mark_price > 0:
        want = min(want, int(limits.max_notional_usd // mark_price))

    if limits.max_loss_usd is not None:
        drawdown = max(0.0, equity_peak - equity)
        if drawdown > limits.max_loss_usd + 1e-9:
            reason = (
                f"max_loss_usd exceeded: drawdown {drawdown:.2f} "
                f"> {limits.max_loss_usd:.2f}"
            )
            return RiskVerdict(ok=False, reason=reason)

    delta = want - position
    if delta > 0 and mark_price > 0:
        # Rough cash check (fees applied at fill layer)
        if delta * mark_price > cash + 1e-9:
            return RiskVerdict(
                ok=False,
                reason=f"insufficient cash for target {want} at mark {mark_price:.4f}",
                clamped_target=position,
            )

    if want != target_shares:
        return RiskVerdict(ok=True, clamped_target=want)
    return RiskVerdict(ok=True, clamped_target=want)


def validate_live_safety(
    *,
    max_loss_usd: float | None,
    max_notional_usd: float | None,
    allow_no_kill: bool,
) -> None:
    """Raise ValueError if live/paper feed would run without required guards."""

    if allow_no_kill:
        return
    if max_loss_usd is None and max_notional_usd is None:
        raise ValueError(
            "live/paper feeds require --max-loss-usd and/or --max-notional-usd "
            "(or pass --allow-no-kill to opt out)"
        )
