from datetime import datetime, timezone
from decimal import Decimal

import pytest

from beombong.data import SignalAction, StrategySignal, TradingCycleResult
from beombong.data.database import create_engine, create_session_factory, init_models
from beombong.data.repository import TradingRepository
from beombong.data.models import OrderExecution, OrderSide


@pytest.mark.asyncio
async def test_repository_records_cycle(tmp_path) -> None:
    db_path = tmp_path / "repo.db"
    engine = create_engine(f"sqlite+aiosqlite:///{db_path}")
    await init_models(engine)
    session_factory = create_session_factory(engine)
    repository = TradingRepository(session_factory)

    signal = StrategySignal(
        market="BTC_KRW",
        action=SignalAction.BUY,
        price=Decimal("100"),
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        reason="test",
        confidence=Decimal("0.5"),
    )
    execution = OrderExecution(
        order_id="A1",
        market="BTC_KRW",
        side=OrderSide.BUY,
        price=Decimal("100"),
        ordered_units=Decimal("0.1"),
        executed_units=Decimal("0.1"),
        fee=Decimal("10"),
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    result = TradingCycleResult(signal=signal, execution=execution, pnl=Decimal("0"))
    await repository.record_cycle(result)

    cycles = await repository.recent_cycles(1)
    assert len(cycles) == 1
    assert cycles[0]["action"] == "buy"

    performance = await repository.daily_performance(signal.timestamp.date())
    assert performance.trade_count == 1
    assert performance.realized_pnl == Decimal("0")
