"""트레이딩 데이터 저장소."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Sequence

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, case, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .models import Candle, TradingCycleResult, TickerSnapshot


class CandleRecord(Base):
    __tablename__ = "market_candles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(20), index=True)
    interval: Mapped[str] = mapped_column(String(20))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    close: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    high: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    low: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    volume: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    value: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("market", "interval", "timestamp", name="uq_market_candle"),)


class TickerRecord(Base):
    __tablename__ = "market_tickers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(20), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    change_rate_24h: Mapped[Decimal] = mapped_column(Numeric(10, 5))
    volume_24h: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("market", "timestamp", name="uq_market_ticker"),)


class SignalRecord(Base):
    __tablename__ = "strategy_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(20), index=True)
    action: Mapped[str] = mapped_column(String(10))
    price: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    confidence: Mapped[Decimal] = mapped_column(Numeric(10, 5))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ExecutionRecord(Base):
    __tablename__ = "order_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    market: Mapped[str] = mapped_column(String(20), index=True)
    side: Mapped[str] = mapped_column(String(5))
    price: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    ordered_units: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    executed_units: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    fee: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class CycleRecord(Base):
    __tablename__ = "trading_cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(20), index=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("strategy_signals.id"))
    execution_id: Mapped[Optional[int]] = mapped_column(ForeignKey("order_executions.id"), nullable=True)
    pnl: Mapped[Decimal] = mapped_column(Numeric(30, 10), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(20))
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    signal: Mapped[SignalRecord] = relationship("SignalRecord")
    execution: Mapped[Optional[ExecutionRecord]] = relationship("ExecutionRecord")


@dataclass(frozen=True)
class DailyPerformance:
    trade_date: date
    realized_pnl: Decimal
    trade_count: int
    winning_trades: int
    losing_trades: int
    best_trade: Optional[Decimal]
    worst_trade: Optional[Decimal]


class TradingRepository:
    """전략 실행 결과와 시세 데이터를 SQLite 에 보관한다."""

    def __init__(self, session_factory: "async_sessionmaker[AsyncSession]") -> None:
        self._session_factory = session_factory

    async def record_candles(self, candles: Sequence[Candle], interval: str) -> None:
        if not candles:
            return
        payload = [
            {
                "market": candle.market,
                "interval": interval,
                "timestamp": candle.timestamp,
                "open": candle.open,
                "close": candle.close,
                "high": candle.high,
                "low": candle.low,
                "volume": candle.volume,
                "value": candle.value,
            }
            for candle in candles
        ]
        async with self._session_factory() as session:
            stmt = sqlite_insert(CandleRecord).values(payload)
            stmt = stmt.on_conflict_do_nothing(index_elements=["market", "interval", "timestamp"])
            await session.execute(stmt)
            await session.commit()

    async def record_ticker(self, snapshot: TickerSnapshot) -> None:
        async with self._session_factory() as session:
            stmt = sqlite_insert(TickerRecord).values(
                market=snapshot.market,
                price=snapshot.price,
                change_rate_24h=snapshot.change_rate_24h,
                volume_24h=snapshot.volume_24h,
                timestamp=snapshot.timestamp,
            ).on_conflict_do_nothing(index_elements=["market", "timestamp"])
            await session.execute(stmt)
            await session.commit()

    async def record_cycle(self, result: TradingCycleResult) -> None:
        async with self._session_factory() as session:
            signal = result.signal
            signal_row = SignalRecord(
                market=signal.market,
                action=signal.action.value,
                price=signal.price,
                confidence=signal.confidence,
                reason=signal.reason,
                created_at=signal.timestamp,
            )
            session.add(signal_row)
            await session.flush()

            execution_row: Optional[ExecutionRecord] = None
            if result.execution is not None:
                execution = result.execution
                execution_row = ExecutionRecord(
                    order_id=execution.order_id,
                    market=execution.market,
                    side=execution.side.value,
                    price=execution.price,
                    ordered_units=execution.ordered_units,
                    executed_units=execution.executed_units,
                    fee=execution.fee,
                    created_at=execution.created_at,
                )
                session.add(execution_row)
                await session.flush()

            cycle_row = CycleRecord(
                market=signal.market,
                run_at=signal.timestamp,
                signal_id=signal_row.id,
                execution_id=execution_row.id if execution_row else None,
                pnl=result.pnl,
                status=self._determine_status(result),
                error=result.error,
                notes=result.notes,
            )
            session.add(cycle_row)
            await session.commit()

    def _determine_status(self, result: TradingCycleResult) -> str:
        if result.error:
            return "error"
        if result.execution is None:
            return "skipped"
        if result.execution.executed_units <= Decimal("0"):
            return "placed"
        return "filled"

    async def recent_cycles(self, limit: int = 20) -> List[dict[str, object]]:
        stmt = (
            select(
                CycleRecord.run_at,
                SignalRecord.market,
                SignalRecord.action,
                SignalRecord.price,
                CycleRecord.status,
                CycleRecord.pnl,
                CycleRecord.error,
            )
            .join(SignalRecord, CycleRecord.signal_id == SignalRecord.id)
            .order_by(CycleRecord.run_at.desc())
            .limit(limit)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return [
            {
                "run_at": row.run_at,
                "market": row.market,
                "action": row.action,
                "price": row.price,
                "status": row.status,
                "pnl": row.pnl,
                "error": row.error,
            }
            for row in rows
        ]

    async def daily_performance(self, target_date: date) -> DailyPerformance:
        stmt = (
            select(
                func.count(CycleRecord.id),
                func.sum(CycleRecord.pnl),
                func.sum(case((CycleRecord.pnl > 0, 1), else_=0)),
                func.sum(case((CycleRecord.pnl < 0, 1), else_=0)),
                func.max(CycleRecord.pnl),
                func.min(CycleRecord.pnl),
            )
            .where(func.date(CycleRecord.run_at) == target_date.isoformat())
        )
        async with self._session_factory() as session:
            row = (await session.execute(stmt)).one()
        trade_count = int(row[0] or 0)
        realized = Decimal(str(row[1])) if row[1] is not None else Decimal("0")
        winning = int(row[2] or 0)
        losing = int(row[3] or 0)
        best = Decimal(str(row[4])) if row[4] is not None else None
        worst = Decimal(str(row[5])) if row[5] is not None else None
        return DailyPerformance(
            trade_date=target_date,
            realized_pnl=realized,
            trade_count=trade_count,
            winning_trades=winning,
            losing_trades=losing,
            best_trade=best,
            worst_trade=worst,
        )


__all__ = [
    "TradingRepository",
    "DailyPerformance",
    "CandleRecord",
    "SignalRecord",
    "ExecutionRecord",
    "CycleRecord",
    "TickerRecord",
]
