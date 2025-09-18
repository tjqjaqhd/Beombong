"""전략 시그널을 주문 실행으로 연결하는 트레이딩 엔진."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Optional, Tuple

from ..clients.bithumb import BithumbClient
from ..data import (
    OrderExecution,
    OrderSide,
    Position,
    SignalAction,
    StrategySignal,
    TradingCycleResult,
)
from ..strategies.base import TradingStrategy
from .portfolio import PortfolioState
from .risk import RiskController


@dataclass(frozen=True)
class RiskParameters:
    """주문 크기와 현금 비중에 대한 위험 관리 설정."""

    max_allocation_pct: Decimal = Decimal("0.3")
    min_cash_reserve_pct: Decimal = Decimal("0.1")
    min_order_value: Decimal = Decimal("5000")
    max_order_value: Optional[Decimal] = None
    daily_loss_limit_pct: Decimal = Decimal("0.05")
    daily_loss_limit_value: Optional[Decimal] = None
    max_consecutive_losses: int = 3
    order_retry_limit: int = 2
    order_retry_delay: float = 1.5

    def __post_init__(self) -> None:
        if not (Decimal("0") < self.max_allocation_pct <= Decimal("1")):
            raise ValueError("max_allocation_pct는 0과 1 사이여야 합니다.")
        if not (Decimal("0") <= self.min_cash_reserve_pct < Decimal("1")):
            raise ValueError("min_cash_reserve_pct는 0 이상 1 미만이어야 합니다.")
        if self.min_order_value < Decimal("0"):
            raise ValueError("min_order_value는 음수일 수 없습니다.")
        if self.max_order_value is not None and self.max_order_value <= Decimal("0"):
            raise ValueError("max_order_value는 양수여야 합니다.")
        if self.daily_loss_limit_pct < Decimal("0"):
            raise ValueError("daily_loss_limit_pct는 음수일 수 없습니다.")
        if self.daily_loss_limit_value is not None and self.daily_loss_limit_value < Decimal("0"):
            raise ValueError("daily_loss_limit_value는 음수일 수 없습니다.")
        if self.max_consecutive_losses < 0:
            raise ValueError("max_consecutive_losses는 0 이상이어야 합니다.")
        if self.order_retry_limit < 0:
            raise ValueError("order_retry_limit는 0 이상이어야 합니다.")
        if self.order_retry_delay < 0:
            raise ValueError("order_retry_delay는 0 이상이어야 합니다.")


class TradingEngine:
    """단일 마켓에 대해 전략을 실행하고 주문을 전송한다."""

    def __init__(
        self,
        *,
        client: BithumbClient,
        strategy: TradingStrategy,
        portfolio: PortfolioState,
        market: str,
        candle_interval: str = "1h",
        candle_count: int = 60,
        risk: Optional[RiskParameters] = None,
        risk_controller: Optional[RiskController] = None,
    ) -> None:
        if candle_count < 10:
            raise ValueError("candle_count는 최소 10 이상이어야 합니다.")
        self._client = client
        self._strategy = strategy
        self._portfolio = portfolio
        self._market = market.upper()
        self._interval = candle_interval
        self._candle_count = candle_count
        self._risk = risk or RiskParameters()
        self._risk_controller = risk_controller or RiskController(self._risk, portfolio)
        self._last_result: Optional[TradingCycleResult] = None

    async def run_cycle(self) -> TradingCycleResult:
        """단일 주기 실행: 데이터 조회 → 전략 판단 → 주문."""

        base_currency, quote_currency = self._split_market()
        candles = await self._client.get_candles(self._market, self._interval, self._candle_count)
        balance = await self._client.get_balance(base_currency, quote_currency)
        self._portfolio.update_from_balance(balance)
        position = self._portfolio.get_position(self._market)
        signal = self._strategy.evaluate(candles, position)
        block_reason = self._risk_controller.evaluate_signal(signal)
        if block_reason:
            hold = StrategySignal.hold(
                market=self._market,
                price=signal.price,
                timestamp=signal.timestamp,
                reason=block_reason,
            )
            result = TradingCycleResult(signal=hold, notes="risk_halt")
            self._risk_controller.record_cycle(result)
            self._last_result = result
            return result

        if signal.action is SignalAction.BUY:
            result = await self._handle_buy(signal, base_currency, quote_currency)
        elif signal.action is SignalAction.SELL:
            result = await self._handle_sell(signal, base_currency, quote_currency, position)
        else:
            result = TradingCycleResult(signal=signal)

        self._risk_controller.record_cycle(result)
        self._last_result = result
        return result

    async def _handle_buy(self, signal: StrategySignal, base_currency: str, quote_currency: str) -> TradingCycleResult:
        price = signal.price
        units = self._calculate_order_units(price)
        if units <= Decimal("0"):
            hold = StrategySignal.hold(
                market=self._market,
                price=price,
                timestamp=signal.timestamp,
                reason="주문 수량 부족",
            )
            return TradingCycleResult(signal=hold)
        try:
            execution = await self._execute_with_retry(
                base_currency,
                quote_currency,
                OrderSide.BUY,
                units,
                price,
            )
        except Exception as exc:  # pragma: no cover - 네트워크 예외 대비
            return TradingCycleResult(signal=signal, error=str(exc))
        pnl = self._portfolio.apply_execution(execution)
        return TradingCycleResult(signal=signal, execution=execution, pnl=pnl)

    async def _handle_sell(
        self,
        signal: StrategySignal,
        base_currency: str,
        quote_currency: str,
        position: Optional[Position],
    ) -> TradingCycleResult:
        if position is None:
            hold = StrategySignal.hold(
                market=self._market,
                price=signal.price,
                timestamp=signal.timestamp,
                reason="매도 가능한 포지션 없음",
            )
            return TradingCycleResult(signal=hold)
        quantity = position.quantity
        if quantity <= Decimal("0"):
            hold = StrategySignal.hold(
                market=self._market,
                price=signal.price,
                timestamp=signal.timestamp,
                reason="보유 수량이 0",
            )
            return TradingCycleResult(signal=hold)
        try:
            execution = await self._execute_with_retry(
                base_currency,
                quote_currency,
                OrderSide.SELL,
                quantity,
                signal.price,
            )
        except Exception as exc:  # pragma: no cover - 네트워크 예외 대비
            return TradingCycleResult(signal=signal, error=str(exc))
        pnl = self._portfolio.apply_execution(execution)
        return TradingCycleResult(signal=signal, execution=execution, pnl=pnl)

    async def _execute_with_retry(
        self,
        base_currency: str,
        quote_currency: str,
        side: OrderSide,
        units: Decimal,
        price: Decimal,
    ) -> OrderExecution:
        attempts = 0
        last_error: Optional[Exception] = None
        while attempts <= self._risk.order_retry_limit:
            try:
                execution = await self._client.place_order(
                    base_currency,
                    side,
                    units=units,
                    price=price,
                    payment_currency=quote_currency,
                )
                return execution
            except Exception as exc:  # pragma: no cover - 네트워크 예외 대비
                last_error = exc
                attempts += 1
                if attempts > self._risk.order_retry_limit:
                    break
                await asyncio.sleep(self._risk.order_retry_delay)
        if last_error is None:  # pragma: no cover - 방어적 코드
            raise RuntimeError("주문 실패: 원인을 확인할 수 없습니다.")
        raise last_error

    def _calculate_order_units(self, price: Decimal) -> Decimal:
        if price <= Decimal("0"):
            return Decimal("0")
        cash = self._portfolio.available_cash()
        if cash <= Decimal("0"):
            return Decimal("0")
        reserve = cash * self._risk.min_cash_reserve_pct
        investable = cash - reserve
        max_by_allocation = cash * self._risk.max_allocation_pct
        investable = min(investable, max_by_allocation)
        if self._risk.max_order_value is not None:
            investable = min(investable, self._risk.max_order_value)
        if investable < self._risk.min_order_value:
            return Decimal("0")
        units = investable / price
        return units.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)

    def _split_market(self) -> Tuple[str, str]:
        if "_" not in self._market:
            return self._market, "KRW"
        base, quote = self._market.split("_", 1)
        return base, quote

    def risk_status(self) -> dict[str, object]:
        return self._risk_controller.status()


__all__ = ["RiskParameters", "TradingEngine"]
