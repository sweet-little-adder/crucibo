"""US equities brokers — dry-run default; Alpaca paper as signed REST option."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from crucibo.live.broker import OrderIntent, OrderResult, OrderSide, OrderStatus
from crucibo.live.reconcile import BrokerSnapshot
from crucibo.settings import alpaca_credentials


class EquityBroker(Protocol):
    """Stock-first broker surface: submit + account/position snapshots."""

    name: str

    def submit(self, intent: OrderIntent) -> OrderResult: ...

    def snapshot(self, *, symbol: str | None = None) -> BrokerSnapshot: ...


@dataclass
class DryRunEquityBroker:
    """Local virtual fills with broker-shaped snapshot (no network)."""

    slip_bps: float = 2.0
    fee_per_share: float = 0.005
    cash: float = 1_000_000.0
    positions: dict[str, int] = field(default_factory=dict)
    order_log: list[dict[str, object]] = field(default_factory=list)
    name: str = "dry_run"

    def submit(self, intent: OrderIntent) -> OrderResult:
        if intent.qty_shares <= 0:
            result = OrderResult(
                client_order_id=intent.client_order_id,
                status=OrderStatus.REJECTED,
                reason="qty must be positive",
            )
            self._log(intent, result)
            return result

        slip_m = self.slip_bps / 10_000.0
        sym = intent.symbol.upper()
        if intent.side == OrderSide.BUY:
            exec_px = intent.mark_price * (1.0 + slip_m)
            fee = intent.qty_shares * self.fee_per_share
            cost = intent.qty_shares * exec_px + fee
            if cost > self.cash + 1e-9:
                result = OrderResult(
                    client_order_id=intent.client_order_id,
                    status=OrderStatus.REJECTED,
                    reason=f"insufficient cash: need {cost:.2f} have {self.cash:.2f}",
                )
                self._log(intent, result)
                return result
            self.cash -= cost
            self.positions[sym] = self.positions.get(sym, 0) + intent.qty_shares
        else:
            exec_px = intent.mark_price * (1.0 - slip_m)
            fee = intent.qty_shares * self.fee_per_share
            held = self.positions.get(sym, 0)
            if intent.qty_shares > held:
                result = OrderResult(
                    client_order_id=intent.client_order_id,
                    status=OrderStatus.REJECTED,
                    reason=f"insufficient shares: need {intent.qty_shares} have {held}",
                )
                self._log(intent, result)
                return result
            proceeds = intent.qty_shares * exec_px - fee
            self.cash += proceeds
            left = held - intent.qty_shares
            if left == 0:
                self.positions.pop(sym, None)
            else:
                self.positions[sym] = left

        result = OrderResult(
            client_order_id=intent.client_order_id,
            status=OrderStatus.FILLED,
            filled_qty=intent.qty_shares,
            exec_price=exec_px,
            fee_cash=fee,
        )
        self._log(intent, result)
        return result

    def _log(self, intent: OrderIntent, result: OrderResult) -> None:
        self.order_log.append(
            {
                "client_order_id": intent.client_order_id,
                "symbol": intent.symbol,
                "side": intent.side.value,
                "qty_shares": intent.qty_shares,
                "mark_price": intent.mark_price,
                "ts_event_ns": intent.ts_event_ns,
                "mode": intent.mode,
                "status": result.status.value,
                "filled_qty": result.filled_qty,
                "exec_price": result.exec_price,
                "fee_cash": result.fee_cash,
                "reason": result.reason,
                "ts_ack_ns": result.ts_ack_ns,
                "broker": self.name,
            }
        )

    def snapshot(self, *, symbol: str | None = None) -> BrokerSnapshot:
        if symbol is None:
            pos = dict(self.positions)
        else:
            sym = symbol.upper()
            pos = {sym: self.positions[sym]} if sym in self.positions else {sym: 0}
        return BrokerSnapshot(cash=self.cash, positions=pos, source=self.name)


@dataclass
class AlpacaPaperBroker:
    """
    Signed REST broker against **Alpaca paper** (US equities, paper capital).

    Env: ``ALPACA_API_KEY`` + ``ALPACA_API_SECRET``.
    Never hits the live money endpoint unless ``live_money=True`` (requires
    ``--i-accept-real-capital`` at CLI).
    """

    api_key: str
    api_secret: str
    live_money: bool = False
    fee_per_share: float = 0.0  # Alpaca commission-free; keep for fee model parity
    timeout_s: float = 30.0
    client: httpx.Client | None = None
    order_log: list[dict[str, object]] = field(default_factory=list)
    name: str = "alpaca_paper"

    def __post_init__(self) -> None:
        if self.live_money:
            self.base_url = "https://api.alpaca.markets"
            self.name = "alpaca_live"
        else:
            self.base_url = "https://paper-api.alpaca.markets"
            self.name = "alpaca_paper"
        self._owns_client = self.client is None
        if self.client is None:
            self.client = httpx.Client(
                base_url=self.base_url,
                headers={
                    "APCA-API-KEY-ID": self.api_key,
                    "APCA-API-SECRET-KEY": self.api_secret,
                    "Accept": "application/json",
                },
                timeout=self.timeout_s,
            )

    def close(self) -> None:
        if self._owns_client and self.client is not None:
            self.client.close()

    def submit(self, intent: OrderIntent) -> OrderResult:
        assert self.client is not None
        side = "buy" if intent.side == OrderSide.BUY else "sell"
        body = {
            "symbol": intent.symbol.upper(),
            "qty": str(intent.qty_shares),
            "side": side,
            "type": "market",
            "time_in_force": "day",
            "client_order_id": intent.client_order_id[:48],
        }
        try:
            resp = self.client.post("/v2/orders", json=body)
        except httpx.HTTPError as exc:
            result = OrderResult(
                client_order_id=intent.client_order_id,
                status=OrderStatus.REJECTED,
                reason=f"http error: {exc}",
            )
            self._log(intent, result, raw=None)
            return result

        if resp.status_code >= 400:
            reason = _alpaca_error(resp)
            result = OrderResult(
                client_order_id=intent.client_order_id,
                status=OrderStatus.REJECTED,
                reason=reason,
            )
            self._log(intent, result, raw=_safe_json(resp))
            return result

        data = resp.json()
        status = str(data.get("status", "")).lower()
        filled_qty = int(float(data.get("filled_qty") or 0))
        filled_avg = data.get("filled_avg_price")
        exec_px = float(filled_avg) if filled_avg not in (None, "") else intent.mark_price

        # Market orders on paper often fill immediately; otherwise treat as NEW/submitted
        if status in {"filled", "partially_filled"} and filled_qty > 0:
            result = OrderResult(
                client_order_id=intent.client_order_id,
                status=OrderStatus.FILLED,
                filled_qty=filled_qty,
                exec_price=exec_px,
                fee_cash=filled_qty * self.fee_per_share,
            )
            self._log(intent, result, raw=data)
            return result

        if status in {"rejected", "canceled", "expired"}:
            result = OrderResult(
                client_order_id=intent.client_order_id,
                status=OrderStatus.REJECTED if status == "rejected" else OrderStatus.CANCELED,
                reason=status,
            )
            self._log(intent, result, raw=data)
            return result

        # Accepted / new / pending — poll once for fill (paper is usually instant)
        order_id = data.get("id")
        if order_id:
            polled = self._poll_order(str(order_id), intent)
            if polled is not None:
                self._log(intent, polled, raw=data)
                return polled

        result = OrderResult(
            client_order_id=intent.client_order_id,
            status=OrderStatus.NEW,
            reason=f"accepted status={status}",
        )
        self._log(intent, result, raw=data)
        return result

    def _poll_order(self, order_id: str, intent: OrderIntent) -> OrderResult | None:
        assert self.client is not None
        try:
            resp = self.client.get(f"/v2/orders/{order_id}")
            if resp.status_code >= 400:
                return None
            data = resp.json()
        except httpx.HTTPError:
            return None
        status = str(data.get("status", "")).lower()
        filled_qty = int(float(data.get("filled_qty") or 0))
        filled_avg = data.get("filled_avg_price")
        if status == "filled" and filled_qty > 0:
            exec_px = float(filled_avg) if filled_avg not in (None, "") else intent.mark_price
            return OrderResult(
                client_order_id=intent.client_order_id,
                status=OrderStatus.FILLED,
                filled_qty=filled_qty,
                exec_price=exec_px,
                fee_cash=filled_qty * self.fee_per_share,
            )
        if status in {"rejected", "canceled", "expired"}:
            return OrderResult(
                client_order_id=intent.client_order_id,
                status=OrderStatus.REJECTED if status == "rejected" else OrderStatus.CANCELED,
                reason=status,
            )
        return None

    def snapshot(self, *, symbol: str | None = None) -> BrokerSnapshot:
        assert self.client is not None
        cash: float | None = None
        try:
            acc = self.client.get("/v2/account")
            if acc.status_code < 400:
                cash = float(acc.json().get("cash", 0))
        except httpx.HTTPError:
            cash = None

        positions: dict[str, int] = {}
        try:
            if symbol:
                resp = self.client.get(f"/v2/positions/{symbol.upper()}")
                if resp.status_code == 200:
                    row = resp.json()
                    positions[symbol.upper()] = int(float(row.get("qty", 0)))
                elif resp.status_code == 404:
                    positions[symbol.upper()] = 0
            else:
                resp = self.client.get("/v2/positions")
                if resp.status_code < 400:
                    for row in resp.json():
                        positions[str(row["symbol"]).upper()] = int(float(row.get("qty", 0)))
        except httpx.HTTPError:
            pass
        return BrokerSnapshot(cash=cash, positions=positions, source=self.name)

    def _log(
        self,
        intent: OrderIntent,
        result: OrderResult,
        *,
        raw: dict[str, Any] | list[Any] | None,
    ) -> None:
        self.order_log.append(
            {
                "client_order_id": intent.client_order_id,
                "symbol": intent.symbol,
                "side": intent.side.value,
                "qty_shares": intent.qty_shares,
                "mark_price": intent.mark_price,
                "ts_event_ns": intent.ts_event_ns,
                "mode": intent.mode,
                "status": result.status.value,
                "filled_qty": result.filled_qty,
                "exec_price": result.exec_price,
                "fee_cash": result.fee_cash,
                "reason": result.reason,
                "ts_ack_ns": result.ts_ack_ns,
                "broker": self.name,
                "raw_keys": list(raw.keys()) if isinstance(raw, dict) else None,
            }
        )


def build_equity_broker(
    *,
    kind: str,
    initial_cash: float = 1_000_000.0,
    slip_bps: float = 2.0,
    fee_per_share: float = 0.005,
    live_money: bool = False,
    client: httpx.Client | None = None,
) -> EquityBroker:
    """Factory: ``dry_run`` (default) or ``alpaca_paper`` / ``alpaca``."""

    key = kind.strip().lower().replace("-", "_")
    if key in {"dry_run", "dryrun", "paper_local"}:
        return DryRunEquityBroker(
            slip_bps=slip_bps,
            fee_per_share=fee_per_share,
            cash=initial_cash,
        )
    if key in {"alpaca_paper", "alpaca", "alpaca_live"}:
        api_key, api_secret = alpaca_credentials()
        use_live = live_money or key == "alpaca_live"
        return AlpacaPaperBroker(
            api_key=api_key,
            api_secret=api_secret,
            live_money=use_live,
            fee_per_share=fee_per_share,
            client=client,
        )
    raise ValueError(f"unknown equity broker {kind!r} (try dry_run | alpaca_paper)")


def _alpaca_error(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        msg = body.get("message") or body.get("code") or body
        return f"alpaca HTTP {resp.status_code}: {msg}"
    except Exception:
        return f"alpaca HTTP {resp.status_code}: {resp.text[:200]}"


def _safe_json(resp: httpx.Response) -> dict[str, Any] | None:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None
