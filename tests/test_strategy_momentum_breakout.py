from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from beombong.data import Candle, Position, SignalAction
from beombong.strategies.momentum_breakout import MomentumBreakoutStrategy


def make_candle(index: int, close: Decimal, volume: Decimal) -> Candle:
    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    timestamp = base_time + timedelta(hours=index)
    return Candle(
        market="BTC_KRW",
        timestamp=timestamp,
        open=close,
        close=close,
        high=close,
        low=close,
        volume=volume,
        value=close * volume,
    )


def build_series(values: list[tuple[Decimal, Decimal]]) -> list[Candle]:
    return [make_candle(i, price, volume) for i, (price, volume) in enumerate(values)]


def test_breakout_strategy_generates_buy_signal() -> None:
    prices = [(Decimal("100"), Decimal("1")) for _ in range(19)]
    prices.append((Decimal("110"), Decimal("1.5")))
    prices.append((Decimal("125"), Decimal("2.0")))
    candles = build_series(prices)
    strategy = MomentumBreakoutStrategy(lookback=20, volume_window=5, breakout_buffer=Decimal("0.01"))

    signal = strategy.evaluate(candles, position=None)

    assert signal.action is SignalAction.BUY
    assert "돌파" in signal.reason
    assert signal.confidence > Decimal("0")


def test_breakout_strategy_requires_volume_confirmation() -> None:
    prices = [(Decimal("100"), Decimal("1.5")) for _ in range(19)]
    prices.append((Decimal("110"), Decimal("1.5")))
    prices.append((Decimal("120"), Decimal("0.5")))
    candles = build_series(prices)
    strategy = MomentumBreakoutStrategy(lookback=20, volume_window=5, volume_multiplier=Decimal("2"))

    signal = strategy.evaluate(candles, position=None)

    assert signal.action is SignalAction.HOLD
    assert signal.reason == "돌파 조건 미충족"


def test_breakout_strategy_signals_take_profit() -> None:
    prices = [(Decimal("100"), Decimal("1")) for _ in range(20)]
    prices.append((Decimal("160"), Decimal("2")))
    candles = build_series(prices)
    position = Position(
        market="BTC_KRW",
        quantity=Decimal("0.5"),
        average_price=Decimal("120"),
        opened_at=candles[0].timestamp,
    )
    strategy = MomentumBreakoutStrategy(lookback=20, take_profit_pct=Decimal("0.2"))

    signal = strategy.evaluate(candles, position)

    assert signal.action is SignalAction.SELL
    assert signal.reason == "목표 수익 도달"


@pytest.mark.parametrize(
    "closing_price, expected_reason",
    [
        (Decimal("95"), "손절 기준 초과"),
        (Decimal("118"), "추세 훼손"),
    ],
)
def test_breakout_strategy_exits_on_loss_or_trend_break(closing_price: Decimal, expected_reason: str) -> None:
    prices = [(Decimal("100"), Decimal("1")) for _ in range(19)]
    prices.append((Decimal("130"), Decimal("1.5")))
    prices.append((closing_price, Decimal("1.2")))
    candles = build_series(prices)
    position = Position(
        market="BTC_KRW",
        quantity=Decimal("1"),
        average_price=Decimal("120"),
        opened_at=candles[5].timestamp,
    )
    strategy = MomentumBreakoutStrategy(lookback=20, stop_loss_pct=Decimal("0.2"), trailing_stop_pct=Decimal("0.08"))

    signal = strategy.evaluate(candles, position)

    assert signal.action is SignalAction.SELL
    assert signal.reason == expected_reason
