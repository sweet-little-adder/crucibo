"""Event-driven backtest runner over OHLCV bars."""

from __future__ import annotations

from dataclasses import dataclass

from crucibo.backtest.broker import SimBroker
from crucibo.backtest.economics import EconomicsConfig
from crucibo.backtest.portfolio import Portfolio, PortfolioView
from crucibo.core.bar import Bar
from crucibo.strategies.base import BarContext, Strategy


@dataclass(frozen=True)
class EquityPoint:
    ts_close_ns: int
    equity: float
    cash: float
    shares: int
    close: float
    drawdown: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "ts_event_ns": self.ts_close_ns,
            "equity_marked": self.equity,
            "cash": self.cash,
            "shares": self.shares,
            "mid_price": self.close,
            "drawdown": self.drawdown,
        }


@dataclass(frozen=True)
class BacktestOutcome:
    fills: list[dict[str, float | int | str]]
    equity_curve: list[dict[str, float | int]]
    final_cash: float
    final_shares: int
    max_drawdown: float

    @property
    def fills_count(self) -> int:
        return len(self.fills)


def run_backtest(
    *,
    strategy: Strategy,
    bars: list[Bar],
    cfg: EconomicsConfig,
) -> BacktestOutcome:
    if not bars:
        raise ValueError("no bars to backtest")

    seq = sorted(bars, key=lambda b: (b.ts_close_ns, b.symbol))
    strategy.prepare(seq)

    portfolio = Portfolio(cash=cfg.initial_cash)
    broker = SimBroker(cfg=cfg, portfolio=portfolio)
    equity_curve: list[EquityPoint] = []
    frozen = tuple(seq)

    pending_target: int | None = None
    pending_signal_index: int | None = None

    for i, bar in enumerate(seq):
        if cfg.latency_bars == 1 and pending_target is not None and pending_signal_index is not None:
            broker.rebalance_to(
                bar=bar,
                target_shares=pending_target,
                exec_price=bar.open,
                signal_bar_index=pending_signal_index,
            )
            pending_target = None
            pending_signal_index = None

        view = PortfolioView(
            cash=portfolio.cash,
            shares=portfolio.shares,
            equity=portfolio.equity_at(bar.close),
            drawdown=portfolio.drawdown(bar.close),
        )
        ctx = BarContext(bar=bar, index=i, bars=frozen, portfolio=view)
        target = strategy.on_bar(ctx)

        if cfg.latency_bars == 0:
            broker.rebalance_to(
                bar=bar,
                target_shares=target,
                exec_price=bar.close,
                signal_bar_index=i,
            )
        else:
            pending_target = target
            pending_signal_index = i

        eq = portfolio.update_peak(bar.close)
        equity_curve.append(
            EquityPoint(
                ts_close_ns=bar.ts_close_ns,
                equity=eq,
                cash=portfolio.cash,
                shares=portfolio.shares,
                close=bar.close,
                drawdown=portfolio.drawdown(bar.close),
            )
        )

    max_dd = max((p.drawdown for p in equity_curve), default=0.0)
    return BacktestOutcome(
        fills=[f.to_dict() for f in broker.fills],
        equity_curve=[p.to_dict() for p in equity_curve],
        final_cash=portfolio.cash,
        final_shares=portfolio.shares,
        max_drawdown=max_dd,
    )


def summarize_backtest(
    cfg: EconomicsConfig,
    outcome: BacktestOutcome,
    *,
    interval: str = "daily",
) -> dict[str, float | int | None]:
    from crucibo.reporting.metrics import compute_metrics

    if not outcome.equity_curve:
        return {
            "equity_start": cfg.initial_cash,
            "equity_end": cfg.initial_cash,
            "pnl_cash": 0.0,
            "return_pct": 0.0,
            "max_drawdown": 0.0,
            "max_drawdown_pct": 0.0,
            "fills_count": 0,
            "sharpe": None,
            "sortino": None,
            "calmar": None,
            "trades_count": 0,
            "win_rate_pct": None,
            "profit_factor": None,
            "expectancy": None,
            "avg_win": None,
            "avg_loss": None,
        }
    return compute_metrics(
        equity_curve=outcome.equity_curve,
        fills=outcome.fills,
        interval=interval,
    )