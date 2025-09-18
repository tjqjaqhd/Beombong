"""포트폴리오 상태와 주문 체결 반영 로직."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Optional

from ..data import BalanceSnapshot, OrderExecution, OrderSide, Position


@dataclass
class PortfolioState:
    """현금 및 포지션 정보를 관리하는 단순 포트폴리오."""

    cash: Decimal = Decimal("0")
    positions: Dict[str, Position] = field(default_factory=dict)
    last_updated: Optional[datetime] = None

    def get_position(self, market: str) -> Optional[Position]:
        return self.positions.get(market)

    def update_from_balance(self, balance: BalanceSnapshot) -> None:
        """빗썸 잔고 응답을 기반으로 현금을 갱신한다."""

        self.cash = balance.available_krw
        market = f"{balance.currency.upper()}_KRW"
        position = self.positions.get(market)
        total_qty = balance.total_currency
        if total_qty <= Decimal("0"):
            if position:
                self.positions.pop(market, None)
        else:
            if position is None:
                position = Position(
                    market=market,
                    quantity=total_qty,
                    average_price=balance.last_price or Decimal("0"),
                    opened_at=datetime.now(timezone.utc),
                )
                self.positions[market] = position
            else:
                position.quantity = total_qty
                # 빗썸 잔고 응답의 `last_price`는 시장 가격이므로 평균 단가를 덮어쓰지 않는다.
        self.last_updated = datetime.now(timezone.utc)

    def apply_execution(self, execution: OrderExecution) -> Decimal:
        """주문 체결 결과를 반영하고 실현 손익을 반환한다."""

        realized_pnl = Decimal("0")
        if execution.executed_units <= Decimal("0"):
            return realized_pnl
        market = execution.market
        position = self.positions.get(market)
        if execution.side is OrderSide.BUY:
            cost = execution.price * execution.executed_units + execution.fee
            if self.cash < cost:
                raise ValueError("현금 잔고가 부족하여 매수 체결을 반영할 수 없습니다.")
            self.cash -= cost
            if position is None:
                position = Position(
                    market=market,
                    quantity=execution.executed_units,
                    average_price=execution.price,
                    opened_at=execution.created_at,
                )
                self.positions[market] = position
            else:
                total_qty = position.quantity + execution.executed_units
                if total_qty <= Decimal("0"):
                    position.quantity = Decimal("0")
                else:
                    weighted_cost = position.average_price * position.quantity + execution.price * execution.executed_units
                    position.quantity = total_qty
                    position.average_price = weighted_cost / total_qty
        else:
            if position is None:
                raise ValueError("보유하지 않은 자산을 매도할 수 없습니다.")
            if execution.executed_units > position.quantity:
                raise ValueError("보유 수량보다 많은 수량을 매도했습니다.")
            revenue = execution.price * execution.executed_units - execution.fee
            cost_basis = position.average_price * execution.executed_units
            realized_pnl = revenue - cost_basis
            self.cash += revenue
            if execution.executed_units == position.quantity:
                self.positions.pop(market, None)
            else:
                position.reduce(execution.executed_units)
        self.last_updated = execution.created_at
        return realized_pnl

    def total_exposure(self) -> Decimal:
        """보유 포지션의 명목 가치 합계를 계산한다."""

        exposure = Decimal("0")
        for position in self.positions.values():
            exposure += position.average_price * position.quantity
        return exposure

    def available_cash(self) -> Decimal:
        """현재 가용 현금을 반환한다."""

        return self.cash

    def total_equity(self) -> Decimal:
        """현금과 포지션의 명목 가치를 합산한 추정 자산."""

        return self.cash + self.total_exposure()


__all__ = ["PortfolioState"]
