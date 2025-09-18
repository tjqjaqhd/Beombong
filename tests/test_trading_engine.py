from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List

import pytest

from beombong.clients.bithumb import OrderSide
from beombong.data import BalanceSnapshot, Candle, OrderExecution, Position, SignalAction, StrategySignal
from beombong.services.portfolio import PortfolioState
from beombong.services.trading import RiskParameters, TradingEngine
from beombong.strategies.base import TradingStrategy
from beombong.strategies.momentum_breakout import MomentumBreakoutStrategy


class FakeBithumbClient:
    def __init__(self, candles: List[Candle], balance: BalanceSnapshot, *, fail_orders: int = 0) -> None:
        self._candles = candles
        self._balance = balance
        self.orders: list[OrderExecution] = []
        self._fail_orders = fail_orders

    async def get_candles(self, market: str, interval: str, count: int) -> List[Candle]:
        return self._candles[-count:]

    async def get_balance(self, currency: str, payment_currency: str) -> BalanceSnapshot:
        return self._balance

    async def place_order(
        self,
        order_currency: str,
        side: OrderSide,
        *,
        units: Decimal,
        price: Decimal,
        payment_currency: str,
    ) -> OrderExecution:
        if self._fail_orders > 0:
            self._fail_orders -= 1
            raise RuntimeError("temporary failure")
        execution = OrderExecution(
            order_id=f"order-{len(self.orders)+1}",
            market=f"{order_currency}_{payment_currency}",
            side=side,
            price=price,
            ordered_units=units,
            executed_units=units,
            fee=Decimal("0"),
            created_at=self._candles[-1].timestamp,
        )
        self.orders.append(execution)
        return execution


def make_candles(prices: list[Decimal], volumes: list[Decimal]) -> List[Candle]:
    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles = []
    for idx, (price, volume) in enumerate(zip(prices, volumes, strict=True)):
        timestamp = base_time + timedelta(hours=idx)
        candles.append(
            Candle(
                market="BTC_KRW",
                timestamp=timestamp,
                open=price,
                close=price,
                high=price,
                low=price,
                volume=volume,
                value=price * volume,
            )
        )
    return candles


class StaticStrategy(TradingStrategy):
    def __init__(self, signals: List[StrategySignal]) -> None:
        self._signals = signals
        self._index = 0

    def evaluate(self, candles: List[Candle], position: Position | None) -> StrategySignal:
        signal = self._signals[self._index]
        self._index = min(len(self._signals) - 1, self._index + 1)
        return signal


@pytest.mark.asyncio
async def test_trading_engine_places_buy_order() -> None:
    prices = [Decimal("100")] * 19 + [Decimal("110"), Decimal("130")]
    volumes = [Decimal("1")] * (len(prices) - 1) + [Decimal("2")]
    candles = make_candles(prices, volumes)
    balance = BalanceSnapshot(
        currency="BTC",
        total_currency=Decimal("0"),
        in_use_currency=Decimal("0"),
        available_currency=Decimal("0"),
        total_krw=Decimal("1000000"),
        in_use_krw=Decimal("100000"),
        available_krw=Decimal("900000"),
        last_price=Decimal("130"),
    )
    client = FakeBithumbClient(candles, balance)
    portfolio = PortfolioState()
    strategy = MomentumBreakoutStrategy(lookback=20, volume_window=5)
    engine = TradingEngine(
        client=client,
        strategy=strategy,
        portfolio=portfolio,
        market="BTC_KRW",
        candle_interval="1h",
        candle_count=len(candles),
        risk=RiskParameters(min_order_value=Decimal("1000")),
    )

    result = await engine.run_cycle()

    assert result.signal.action is SignalAction.BUY
    assert len(client.orders) == 1, "주문이 하나만 생성되어야 합니다."
    execution = client.orders[0]
    assert execution.side is OrderSide.BUY
    assert portfolio.get_position("BTC_KRW") is not None
    assert portfolio.available_cash() < Decimal("900000")


@pytest.mark.asyncio
async def test_trading_engine_places_sell_order() -> None:
    prices = [Decimal("100")] * 19 + [Decimal("110"), Decimal("160")]
    volumes = [Decimal("1.5")] * len(prices)
    candles = make_candles(prices, volumes)
    position = Position(
        market="BTC_KRW",
        quantity=Decimal("1"),
        average_price=Decimal("120"),
        opened_at=candles[0].timestamp,
    )
    balance = BalanceSnapshot(
        currency="BTC",
        total_currency=Decimal("1"),
        in_use_currency=Decimal("0"),
        available_currency=Decimal("1"),
        total_krw=Decimal("200000"),
        in_use_krw=Decimal("0"),
        available_krw=Decimal("200000"),
        last_price=None,
    )
    client = FakeBithumbClient(candles, balance)
    portfolio = PortfolioState()
    portfolio.positions[position.market] = position
    strategy = MomentumBreakoutStrategy(lookback=20, take_profit_pct=Decimal("0.2"))
    engine = TradingEngine(
        client=client,
        strategy=strategy,
        portfolio=portfolio,
        market="BTC_KRW",
        candle_interval="1h",
        candle_count=len(candles),
        risk=RiskParameters(min_order_value=Decimal("100")),
    )

    result = await engine.run_cycle()

    assert result.signal.action is SignalAction.SELL
    assert len(client.orders) == 1
    execution = client.orders[0]
    assert execution.side is OrderSide.SELL
    assert portfolio.get_position("BTC_KRW") is None
    assert portfolio.available_cash() > Decimal("200000")


@pytest.mark.asyncio
async def test_trading_engine_retries_on_order_failure() -> None:
    prices = [Decimal("100")] * 21
    volumes = [Decimal("1")] * 21
    candles = make_candles(prices, volumes)
    balance = BalanceSnapshot(
        currency="BTC",
        total_currency=Decimal("0"),
        in_use_currency=Decimal("0"),
        available_currency=Decimal("0"),
        total_krw=Decimal("1000000"),
        in_use_krw=Decimal("0"),
        available_krw=Decimal("1000000"),
        last_price=Decimal("100"),
    )
    client = FakeBithumbClient(candles, balance, fail_orders=1)
    portfolio = PortfolioState(cash=Decimal("1000000"))
    signal = StrategySignal(
        market="BTC_KRW",
        action=SignalAction.BUY,
        price=Decimal("100"),
        timestamp=candles[-1].timestamp,
        reason="test",
    )
    strategy = StaticStrategy([signal])
    engine = TradingEngine(
        client=client,
        strategy=strategy,
        portfolio=portfolio,
        market="BTC_KRW",
        candle_interval="1h",
        candle_count=len(candles),
        risk=RiskParameters(min_order_value=Decimal("1000"), order_retry_limit=2, order_retry_delay=0),
    )

    result = await engine.run_cycle()

    assert result.execution is not None
    assert len(client.orders) == 1


@pytest.mark.asyncio
async def test_trading_engine_halts_after_daily_loss_limit() -> None:
    prices = [Decimal("200")] * 19 + [Decimal("190"), Decimal("180")]
    volumes = [Decimal("1")] * len(prices)
    candles = make_candles(prices, volumes)
    balance = BalanceSnapshot(
        currency="BTC",
        total_currency=Decimal("1"),
        in_use_currency=Decimal("0"),
        available_currency=Decimal("1"),
        total_krw=Decimal("500000"),
        in_use_krw=Decimal("0"),
        available_krw=Decimal("500000"),
        last_price=Decimal("180"),
    )
    client = FakeBithumbClient(candles, balance)
    portfolio = PortfolioState(cash=Decimal("500000"))
    portfolio.positions["BTC_KRW"] = Position(
        market="BTC_KRW",
        quantity=Decimal("1"),
        average_price=Decimal("200"),
        opened_at=candles[0].timestamp,
    )
    sell_signal = StrategySignal(
        market="BTC_KRW",
        action=SignalAction.SELL,
        price=Decimal("180"),
        timestamp=candles[-1].timestamp,
        reason="손절",
    )
    buy_signal = StrategySignal(
        market="BTC_KRW",
        action=SignalAction.BUY,
        price=Decimal("180"),
        timestamp=candles[-1].timestamp,
        reason="재진입",
    )
    strategy = StaticStrategy([sell_signal, buy_signal])
    engine = TradingEngine(
        client=client,
        strategy=strategy,
        portfolio=portfolio,
        market="BTC_KRW",
        candle_interval="1h",
        candle_count=len(candles),
        risk=RiskParameters(
            min_order_value=Decimal("1000"),
            daily_loss_limit_value=Decimal("10"),
            max_consecutive_losses=1,
        ),
    )

    first = await engine.run_cycle()
    assert first.execution is not None
    assert first.pnl < Decimal("0")

    second = await engine.run_cycle()
    assert second.signal.action is SignalAction.HOLD
    assert second.signal.reason == "일일 손실 한도 초과"
