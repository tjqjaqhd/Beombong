"""리스크 관리 상태와 통제 로직."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from ..data import SignalAction, StrategySignal, TradingCycleResult
from .portfolio import PortfolioState

if TYPE_CHECKING:  # pragma: no cover
    from .trading import RiskParameters


@dataclass
class RiskState:
    """일별 리스크 상태 추적."""

    trading_day: date
    starting_equity: Decimal
    realized_pnl: Decimal = Decimal("0")
    consecutive_losses: int = 0
    halted: bool = False
    last_halt_reason: Optional[str] = None


class RiskController:
    """일일 손실 한도와 연속 손실 제약을 추적한다."""

    def __init__(self, params: "RiskParameters", portfolio: PortfolioState) -> None:
        self._params = params
        self._portfolio = portfolio
        self._state: Optional[RiskState] = None

    def ensure_trading_day(self, current_time: Optional[datetime] = None) -> None:
        """현재 날짜 기준으로 상태를 초기화한다."""

        now = current_time or datetime.now(timezone.utc)
        trading_day = now.date()
        if self._state is not None and self._state.trading_day == trading_day:
            return
        starting_equity = self._portfolio.total_equity()
        self._state = RiskState(trading_day=trading_day, starting_equity=starting_equity)

    def evaluate_signal(self, signal: StrategySignal) -> Optional[str]:
        """주문 실행 전 리스크 한도를 확인하고 사유를 반환한다."""

        self.ensure_trading_day(signal.timestamp)
        if self._state is None:
            return None
        if self._state.halted:
            return self._state.last_halt_reason or "리스크 제한으로 중단됨"
        if signal.action is SignalAction.HOLD:
            return None
        limit = self._daily_loss_limit()
        if limit is not None and self._state.realized_pnl <= -limit:
            self._state.halted = True
            self._state.last_halt_reason = "일일 손실 한도 초과"
            return self._state.last_halt_reason
        if (
            self._params.max_consecutive_losses
            and self._state.consecutive_losses >= self._params.max_consecutive_losses
        ):
            self._state.halted = True
            self._state.last_halt_reason = "연속 손실 한도 초과"
            return self._state.last_halt_reason
        return None

    def record_cycle(self, result: TradingCycleResult) -> None:
        """사이클 결과를 반영해 손실 한도 및 연속 손실을 갱신한다."""

        self.ensure_trading_day(result.signal.timestamp)
        if self._state is None:
            return
        if result.pnl != Decimal("0"):
            self._state.realized_pnl += result.pnl
            if result.pnl < Decimal("0"):
                self._state.consecutive_losses += 1
            elif result.pnl > Decimal("0"):
                self._state.consecutive_losses = 0
        if result.notes == "manual_halt":
            self._state.halted = True
            self._state.last_halt_reason = result.error or "수동 중지"
            return
        limit = self._daily_loss_limit()
        if limit is not None and self._state.realized_pnl <= -limit:
            self._state.halted = True
            self._state.last_halt_reason = "일일 손실 한도 초과"
        elif (
            self._params.max_consecutive_losses
            and self._state.consecutive_losses >= self._params.max_consecutive_losses
        ):
            self._state.halted = True
            self._state.last_halt_reason = (
                f"연속 손실 {self._state.consecutive_losses}회 초과"
            )

    def halt(self, reason: str) -> None:
        """수동으로 트레이딩을 중단한다."""

        self.ensure_trading_day()
        if self._state is None:
            return
        self._state.halted = True
        self._state.last_halt_reason = reason

    def is_halted(self) -> bool:
        self.ensure_trading_day()
        return bool(self._state and self._state.halted)

    def status(self) -> dict[str, object]:
        self.ensure_trading_day()
        state = self._state
        return {
            "trading_day": state.trading_day.isoformat() if state else None,
            "starting_equity": str(state.starting_equity) if state else None,
            "realized_pnl": str(state.realized_pnl) if state else "0",
            "consecutive_losses": state.consecutive_losses if state else 0,
            "halted": state.halted if state else False,
            "halt_reason": state.last_halt_reason,
            "daily_loss_limit": str(self._daily_loss_limit()) if state else None,
        }

    def _daily_loss_limit(self) -> Optional[Decimal]:
        if self._state is None:
            return None
        if self._params.daily_loss_limit_value and self._params.daily_loss_limit_value > Decimal("0"):
            return self._params.daily_loss_limit_value
        if self._params.daily_loss_limit_pct > Decimal("0") and self._state.starting_equity > Decimal("0"):
            return self._state.starting_equity * self._params.daily_loss_limit_pct
        return None


__all__ = ["RiskController", "RiskState"]
