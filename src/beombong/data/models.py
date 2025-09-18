"""거래 전략과 포트폴리오에서 사용하는 공용 데이터 모델."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Mapping, Optional, Sequence


def _to_decimal(value: object) -> Decimal:
    """다양한 입력을 Decimal 로 변환한다."""

    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        return Decimal(value)
    raise TypeError(f"Decimal 로 변환할 수 없는 타입: {type(value)!r}")


@dataclass(frozen=True, slots=True)
class Candle:
    """단일 캔들스틱 데이터."""

    market: str
    timestamp: datetime
    open: Decimal
    close: Decimal
    high: Decimal
    low: Decimal
    volume: Decimal
    value: Decimal

    @classmethod
    def from_bithumb_payload(cls, market: str, payload: Sequence[object]) -> "Candle":
        """빗썸 캔들스틱 배열을 Candle 로 변환한다."""

        if len(payload) < 7:
            raise ValueError("캔들 데이터의 요소 수가 부족합니다.")
        timestamp_raw, open_, close_, high, low, volume, value = payload[:7]
        timestamp = datetime.fromtimestamp(float(timestamp_raw) / 1000, tz=timezone.utc)
        return cls(
            market=market,
            timestamp=timestamp,
            open=_to_decimal(open_),
            close=_to_decimal(close_),
            high=_to_decimal(high),
            low=_to_decimal(low),
            volume=_to_decimal(volume),
            value=_to_decimal(value),
        )


@dataclass(frozen=True, slots=True)
class TickerSnapshot:
    """웹소켓 또는 REST 기반 시세 스냅샷."""

    market: str
    price: Decimal
    change_rate_24h: Decimal
    volume_24h: Decimal
    timestamp: datetime


class OrderSide(str, Enum):
    """주문 방향."""

    BUY = "bid"
    SELL = "ask"

    @property
    def is_buy(self) -> bool:
        return self is OrderSide.BUY

    @property
    def is_sell(self) -> bool:
        return self is OrderSide.SELL


class SignalAction(str, Enum):
    """전략 의사결정 종류."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass(frozen=True, slots=True)
class StrategySignal:
    """전략에서 생성한 매매 시그널."""

    market: str
    action: SignalAction
    price: Decimal
    timestamp: datetime
    reason: str
    confidence: Decimal = Decimal("0")

    @classmethod
    def hold(cls, market: str, price: Decimal, timestamp: datetime, reason: str) -> "StrategySignal":
        return cls(market=market, action=SignalAction.HOLD, price=price, timestamp=timestamp, reason=reason)


@dataclass(slots=True)
class Position:
    """보유 포지션."""

    market: str
    quantity: Decimal
    average_price: Decimal
    opened_at: datetime

    def reduce(self, quantity: Decimal) -> None:
        new_quantity = self.quantity - quantity
        if new_quantity < Decimal("0"):
            raise ValueError("보유 수량보다 많은 수량을 차감할 수 없습니다.")
        self.quantity = new_quantity


@dataclass(frozen=True, slots=True)
class BalanceSnapshot:
    """빗썸 잔고 조회 결과."""

    currency: str
    total_currency: Decimal
    in_use_currency: Decimal
    available_currency: Decimal
    total_krw: Decimal
    in_use_krw: Decimal
    available_krw: Decimal
    last_price: Optional[Decimal] = None

    @classmethod
    def from_payload(cls, currency: str, payload: Mapping[str, object]) -> "BalanceSnapshot":
        if not isinstance(payload, Mapping):
            raise TypeError("balance 응답 포맷이 올바르지 않습니다.")
        cur = currency.lower()
        try:
            total_currency = _to_decimal(payload[f"total_{cur}"])
            in_use_currency = _to_decimal(payload[f"in_use_{cur}"])
            available_currency = _to_decimal(payload[f"available_{cur}"])
        except KeyError as exc:  # pragma: no cover - defensive branch
            raise KeyError(f"잔고 응답에 {exc.args[0]} 키가 없습니다.") from exc
        last_price = payload.get("xcoin_last")
        return cls(
            currency=currency.upper(),
            total_currency=total_currency,
            in_use_currency=in_use_currency,
            available_currency=available_currency,
            total_krw=_to_decimal(payload.get("total_krw", "0")),
            in_use_krw=_to_decimal(payload.get("in_use_krw", "0")),
            available_krw=_to_decimal(payload.get("available_krw", "0")),
            last_price=_to_decimal(last_price) if last_price is not None else None,
        )


@dataclass(frozen=True, slots=True)
class OrderExecution:
    """주문 집행 결과."""

    order_id: str
    market: str
    side: OrderSide
    price: Decimal
    ordered_units: Decimal
    executed_units: Decimal
    fee: Decimal
    created_at: datetime

    @property
    def is_filled(self) -> bool:
        return self.executed_units > Decimal("0") and self.executed_units >= self.ordered_units


@dataclass(frozen=True, slots=True)
class TradingCycleResult:
    """트레이딩 루프 한 사이클의 결과."""

    signal: StrategySignal
    execution: Optional[OrderExecution] = None
    pnl: Decimal = Decimal("0")
    error: Optional[str] = None
    notes: Optional[str] = None


__all__ = [
    "BalanceSnapshot",
    "Candle",
    "TickerSnapshot",
    "OrderExecution",
    "OrderSide",
    "Position",
    "SignalAction",
    "StrategySignal",
    "TradingCycleResult",
]
