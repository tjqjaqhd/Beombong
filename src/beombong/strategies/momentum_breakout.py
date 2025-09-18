"""추세 돌파 기반 모멘텀 전략 구현."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Sequence

from ..data import Candle, Position, SignalAction, StrategySignal
from .base import TradingStrategy


class MomentumBreakoutStrategy(TradingStrategy):
    """일정 기간 고점을 돌파할 때 진입하고 손절/이익실현을 적용하는 전략."""

    def __init__(
        self,
        *,
        lookback: int = 20,
        volume_window: int = 10,
        breakout_buffer: Decimal = Decimal("0.01"),
        volume_multiplier: Decimal = Decimal("1.2"),
        stop_loss_pct: Decimal = Decimal("0.02"),
        take_profit_pct: Decimal = Decimal("0.05"),
        trailing_stop_pct: Decimal = Decimal("0.015"),
        cooldown_bars: int = 3,
    ) -> None:
        if lookback < 3:
            raise ValueError("lookback 값은 3 이상이어야 합니다.")
        if volume_window < 1:
            raise ValueError("volume_window 값은 1 이상이어야 합니다.")
        self.lookback = lookback
        self.volume_window = volume_window
        self.breakout_buffer = breakout_buffer
        self.volume_multiplier = volume_multiplier
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.trailing_stop_pct = trailing_stop_pct
        self.cooldown_bars = cooldown_bars
        self._last_buy_bar: Optional[int] = None
        self._last_sell_bar: Optional[int] = None

    def reset(self) -> None:
        self._last_buy_bar = None
        self._last_sell_bar = None

    def evaluate(self, candles: Sequence[Candle], position: Optional[Position]) -> StrategySignal:
        if not candles:
            raise ValueError("최소 한 개 이상의 캔들이 필요합니다.")
        latest = candles[-1]
        bar_index = len(candles)
        if len(candles) <= self.lookback:
            return StrategySignal.hold(latest.market, latest.close, latest.timestamp, "데이터가 부족합니다.")

        if position is None:
            if self._last_buy_bar is not None and bar_index - self._last_buy_bar <= self.cooldown_bars:
                return StrategySignal.hold(latest.market, latest.close, latest.timestamp, "쿨다운 대기 중")
            if self._last_sell_bar is not None and bar_index - self._last_sell_bar <= self.cooldown_bars:
                return StrategySignal.hold(latest.market, latest.close, latest.timestamp, "청산 후 재진입 대기")
            breakout_window = candles[-(self.lookback + 1) : -1]
            highest_high = max(candle.high for candle in breakout_window)
            threshold = highest_high * (Decimal("1") + self.breakout_buffer)
            avg_volume = self._average_volume(candles)
            volume_condition = avg_volume == Decimal("0") or latest.volume >= avg_volume * self.volume_multiplier
            if latest.close >= threshold and volume_condition:
                confidence = self._compute_confidence(latest.close, threshold)
                self._last_buy_bar = bar_index
                return StrategySignal(
                    market=latest.market,
                    action=SignalAction.BUY,
                    price=latest.close,
                    timestamp=latest.timestamp,
                    reason=f"{self.lookback}봉 고점 돌파 확인",
                    confidence=confidence,
                )
            return StrategySignal.hold(latest.market, latest.close, latest.timestamp, "돌파 조건 미충족")

        return self._evaluate_with_position(candles, position)

    def _average_volume(self, candles: Sequence[Candle]) -> Decimal:
        window = candles[-min(len(candles), self.volume_window) :]
        if not window:
            return Decimal("0")
        total = sum((candle.volume for candle in window), Decimal("0"))
        return total / Decimal(len(window))

    def _compute_confidence(self, price: Decimal, threshold: Decimal) -> Decimal:
        if threshold <= Decimal("0"):
            return Decimal("0")
        if self.breakout_buffer <= Decimal("0"):
            return Decimal("1")
        diff = price - threshold
        if diff <= Decimal("0"):
            return Decimal("0")
        scaled = diff / (threshold * self.breakout_buffer)
        return min(Decimal("1"), scaled)

    def _evaluate_with_position(self, candles: Sequence[Candle], position: Position) -> StrategySignal:
        latest = candles[-1]
        bar_index = len(candles)
        profit_target = position.average_price * (Decimal("1") + self.take_profit_pct)
        if latest.close >= profit_target:
            self._last_sell_bar = bar_index
            return StrategySignal(
                market=latest.market,
                action=SignalAction.SELL,
                price=latest.close,
                timestamp=latest.timestamp,
                reason="목표 수익 도달",
                confidence=Decimal("1"),
            )

        loss_limit = position.average_price * (Decimal("1") - self.stop_loss_pct)
        if latest.close <= loss_limit:
            self._last_sell_bar = bar_index
            return StrategySignal(
                market=latest.market,
                action=SignalAction.SELL,
                price=latest.close,
                timestamp=latest.timestamp,
                reason="손절 기준 초과",
                confidence=Decimal("1"),
            )

        highs_since_entry = [candle.high for candle in candles if candle.timestamp >= position.opened_at]
        if not highs_since_entry:
            highs_since_entry = [latest.high]
        highest_since_entry = max(highs_since_entry)
        trailing_stop = highest_since_entry * (Decimal("1") - self.trailing_stop_pct)
        if latest.close <= trailing_stop:
            self._last_sell_bar = bar_index
            return StrategySignal(
                market=latest.market,
                action=SignalAction.SELL,
                price=latest.close,
                timestamp=latest.timestamp,
                reason="추세 훼손",
                confidence=Decimal("0.5"),
            )

        if self._last_sell_bar is not None and bar_index - self._last_sell_bar <= self.cooldown_bars:
            return StrategySignal.hold(latest.market, latest.close, latest.timestamp, "청산 직후 대기")
        return StrategySignal.hold(latest.market, latest.close, latest.timestamp, "보유 유지")


__all__ = ["MomentumBreakoutStrategy"]
