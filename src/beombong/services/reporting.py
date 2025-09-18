"""성과 리포트 생성기."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..data import DailyPerformance
from ..data.repository import TradingRepository


@dataclass(frozen=True)
class ReportContext:
    performance: DailyPerformance

    def format_markdown(self) -> str:
        realized = f"{self.performance.realized_pnl:.0f}"
        win_rate = (
            self.performance.winning_trades / self.performance.trade_count * 100
            if self.performance.trade_count
            else 0
        )
        lines = [
            f"* 거래일: {self.performance.trade_date.isoformat()}",
            f"* 실현 손익: {realized} KRW",
            (
                "* 거래 횟수: "
                f"{self.performance.trade_count} (승 {self.performance.winning_trades} / 패 {self.performance.losing_trades})"
            ),
            f"* 승률: {win_rate:.1f}%",
        ]
        if self.performance.best_trade is not None:
            lines.append(f"* 최대 이익: {self.performance.best_trade:.0f} KRW")
        if self.performance.worst_trade is not None:
            lines.append(f"* 최대 손실: {self.performance.worst_trade:.0f} KRW")
        return "\n".join(lines)


class PerformanceReporter:
    """일일 성과 리포트를 생성한다."""

    def __init__(self, repository: TradingRepository) -> None:
        self._repository = repository

    async def generate(self, target_date: date) -> ReportContext:
        performance = await self._repository.daily_performance(target_date)
        return ReportContext(performance=performance)


__all__ = ["PerformanceReporter", "ReportContext"]
