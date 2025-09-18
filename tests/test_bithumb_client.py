import base64
import hashlib
import hmac
from decimal import Decimal

import httpx
import pytest
import respx

from beombong.clients.bithumb import (
    BithumbClient,
    BithumbCredentialsError,
    OrderSide,
    Ticker,
)
from beombong.config.settings import AppSettings
from beombong.data import Candle


@pytest.mark.asyncio
async def test_get_ticker_returns_parsed_model(respx_mock: respx.MockRouter) -> None:
    mock_response = {
        "status": "0000",
        "data": {
            "opening_price": "100",
            "closing_price": "110",
            "min_price": "90",
            "max_price": "120",
            "units_traded": "3.5",
            "acc_trade_value": "350",
            "prev_closing_price": "95",
            "units_traded_24H": "7",
            "acc_trade_value_24H": "700",
            "fluctate_24H": "10",
            "fluctate_rate_24H": "5",
            "date": "1700000000000",
        },
    }
    route = respx_mock.get("https://api.bithumb.com/public/ticker/BTC").mock(
        return_value=httpx.Response(200, json=mock_response)
    )
    async with BithumbClient() as client:
        ticker = await client.get_ticker("BTC")
    assert route.called
    assert isinstance(ticker, Ticker)
    assert ticker.market == "BTC"
    assert ticker.closing_price == Decimal("110")
    assert ticker.timestamp.tzinfo is not None


@pytest.mark.asyncio
async def test_private_post_generates_expected_signature(respx_mock: respx.MockRouter) -> None:
    settings = AppSettings(
        bithumb_api_key="test-key",
        bithumb_api_secret="secret",
    )
    route = respx_mock.post("https://api.bithumb.com/info/balance").mock(
        return_value=httpx.Response(200, json={"status": "0000", "data": {"total_krw": "1000"}})
    )
    async with BithumbClient(settings=settings, nonce_factory=lambda: "12345") as client:
        response = await client.private_post("/info/balance", {"order_currency": "BTC"})

    assert route.called
    request = route.calls.last.request
    assert request.headers["Api-Key"] == "test-key"
    assert request.headers["Api-Nonce"] == "12345"
    expected_payload = "\x00".join(
        [
            "/info/balance",
            "endpoint=%2Finfo%2Fbalance&order_currency=BTC",
            "12345",
        ]
    )
    expected_signature = base64.b64encode(
        hmac.new(b"secret", expected_payload.encode(), hashlib.sha512).digest()
    ).decode()
    assert request.headers["Api-Sign"] == expected_signature
    assert request.content.decode() == "endpoint=%2Finfo%2Fbalance&order_currency=BTC"
    assert response["data"]["total_krw"] == "1000"


@pytest.mark.asyncio
async def test_private_post_requires_credentials() -> None:
    async with BithumbClient() as client:
        with pytest.raises(BithumbCredentialsError):
            await client.private_post("/info/balance")


@pytest.mark.asyncio
async def test_get_candles_returns_models(respx_mock: respx.MockRouter) -> None:
    mock_response = {
        "status": "0000",
        "data": [
            ["1700000000000", "100", "105", "110", "95", "1.5", "150"],
            ["1700003600000", "105", "115", "120", "100", "2.0", "230"],
        ],
    }
    route = respx_mock.get("https://api.bithumb.com/public/candlestick/BTC_KRW/1h").mock(
        return_value=httpx.Response(200, json=mock_response)
    )
    async with BithumbClient() as client:
        candles = await client.get_candles("BTC_KRW", "1h", count=2)

    assert route.called
    assert isinstance(candles[0], Candle)
    assert candles[0].open == Decimal("100")
    assert candles[-1].close == Decimal("115")
    assert candles[-1].timestamp.tzinfo is not None


@pytest.mark.asyncio
async def test_get_balance_parses_numeric_fields(respx_mock: respx.MockRouter) -> None:
    settings = AppSettings(
        bithumb_api_key="key",
        bithumb_api_secret="secret",
    )
    mock_response = {
        "status": "0000",
        "data": {
            "total_krw": "1000000",
            "in_use_krw": "100000",
            "available_krw": "900000",
            "total_btc": "0.5",
            "in_use_btc": "0.1",
            "available_btc": "0.4",
            "xcoin_last": "35000000",
        },
    }
    route = respx_mock.post("https://api.bithumb.com/info/balance").mock(
        return_value=httpx.Response(200, json=mock_response)
    )
    async with BithumbClient(settings=settings, nonce_factory=lambda: "123") as client:
        balance = await client.get_balance("BTC")

    assert route.called
    assert balance.currency == "BTC"
    assert balance.available_currency == Decimal("0.4")
    assert balance.available_krw == Decimal("900000")
    assert balance.last_price == Decimal("35000000")


@pytest.mark.asyncio
async def test_place_order_builds_payload_and_returns_execution(respx_mock: respx.MockRouter) -> None:
    settings = AppSettings(
        bithumb_api_key="key",
        bithumb_api_secret="secret",
    )
    mock_response = {
        "status": "0000",
        "data": {
            "order_id": "A0001",
            "units": "0.1",
            "units_remaining": "0",
            "price": "1000000",
            "fee": "1000",
        },
    }
    route = respx_mock.post("https://api.bithumb.com/trade/place").mock(
        return_value=httpx.Response(200, json=mock_response)
    )
    async with BithumbClient(settings=settings, nonce_factory=lambda: "42") as client:
        execution = await client.place_order(
            "BTC",
            OrderSide.BUY,
            units=Decimal("0.1"),
            price=Decimal("1000000"),
        )

    assert route.called
    request = route.calls.last.request
    body = request.content.decode()
    assert "type=bid" in body
    assert "units=0.1" in body
    assert "price=1000000" in body
    assert execution.order_id == "A0001"
    assert execution.executed_units == Decimal("0.1")
    assert execution.fee == Decimal("1000")
    assert execution.is_filled


@pytest.mark.asyncio
async def test_cancel_order_posts_required_fields(respx_mock: respx.MockRouter) -> None:
    settings = AppSettings(
        bithumb_api_key="key",
        bithumb_api_secret="secret",
    )
    mock_response = {"status": "0000", "data": {"order_id": "A0001"}}
    route = respx_mock.post("https://api.bithumb.com/trade/cancel").mock(
        return_value=httpx.Response(200, json=mock_response)
    )
    async with BithumbClient(settings=settings, nonce_factory=lambda: "1") as client:
        result = await client.cancel_order("A0001", "BTC", OrderSide.SELL)

    assert route.called
    request = route.calls.last.request
    assert "type=ask" in request.content.decode()
    assert result is True
