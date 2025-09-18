"""전략 공통 인터페이스."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Sequence

from ..data import Candle, Position, StrategySignal


class TradingStrategy(ABC):
    """모든 매매 전략이 구현해야 하는 기본 인터페이스."""

    @abstractmethod
    def evaluate(self, candles: Sequence[Candle], position: Optional[Position]) -> StrategySignal:
        """주어진 캔들 데이터와 현재 포지션을 바탕으로 다음 행동을 결정한다."""

    def reset(self) -> None:
        """전략 내부 상태를 초기화한다."""

        # 기본 구현 없음.
        return None


__all__ = ["TradingStrategy"]
