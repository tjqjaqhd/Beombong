"""빗썸 Open API 연동 클라이언트."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, List, Mapping, MutableMapping, Optional
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, Field
from pydantic import ConfigDict

from ..config.settings import AppSettings, get_settings
from ..data import BalanceSnapshot, Candle, OrderExecution, OrderSide


class BithumbAPIError(RuntimeError):
    """빗썸 API 오류 응답."""

    def __init__(self, status: str, message: Optional[str] = None) -> None:
        self.status = status
        self.message = message
        super().__init__(f"Bithumb API 오류[{status}]: {message or '알 수 없는 오류'}")


class BithumbCredentialsError(RuntimeError):
    """API 키가 필요한 호출에 인증 정보가 없을 때 발생."""

    def __init__(self) -> None:
        super().__init__("빗썸 API Key와 Secret이 설정되어야 합니다.")


class Ticker(BaseModel):
    """빗썸 시세 틱 데이터."""

    model_config = ConfigDict(populate_by_name=True)

    market: str
    opening_price: Decimal
    closing_price: Decimal
    min_price: Decimal
    max_price: Decimal
    units_traded: Decimal
    acc_trade_value: Decimal
    prev_closing_price: Decimal
    units_traded_24h: Decimal = Field(alias="units_traded_24H")
    acc_trade_value_24h: Decimal = Field(alias="acc_trade_value_24H")
    fluctate_24h: Decimal = Field(alias="fluctate_24H")
    fluctate_rate_24h: Decimal = Field(alias="fluctate_rate_24H")
    timestamp: datetime = Field(alias="date")

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
        if isinstance(value, str) and value.isdigit():
            return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
        raise ValueError("date 필드를 변환할 수 없습니다.")

    @classmethod
    def from_payload(cls, market: str, payload: Mapping[str, Any]) -> "Ticker":
        data: MutableMapping[str, Any] = dict(payload)
        data["market"] = market
        data["date"] = cls._parse_timestamp(data["date"])
        return cls.model_validate(data)


@dataclass(slots=True)
class _PrivateRequestContext:
    endpoint: str
    body: Mapping[str, Any]
    nonce: str
    signature: str


class BithumbClient:
    """빗썸 API 호출을 담당하는 비동기 클라이언트."""

    def __init__(
        self,
        settings: Optional[AppSettings] = None,
        *,
        client: Optional[httpx.AsyncClient] = None,
        nonce_factory: Optional[Callable[[], str]] = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._api_key = self._settings.bithumb_api_key
        self._api_secret = self._settings.bithumb_api_secret
        self._client = client or httpx.AsyncClient(
            base_url=str(self._settings.bithumb_base_url),
            timeout=self._settings.http_timeout,
        )
        self._owns_client = client is None
        self._nonce_factory = nonce_factory or self._default_nonce

    async def __aenter__(self) -> "BithumbClient":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """내부 HTTP 클라이언트를 종료한다."""

        if self._owns_client:
            await self._client.aclose()

    async def get_ticker(self, market: str) -> Ticker:
        """특정 마켓의 현재가 정보를 조회한다."""

        response = await self._client.get(f"/public/ticker/{market}")
        payload = self._decode_response(response)
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise BithumbAPIError("invalid", "ticker 데이터 형식이 올바르지 않습니다.")
        return Ticker.from_payload(market, data)

    async def get_candles(self, market: str, interval: str, count: int = 60) -> List[Candle]:
        """특정 마켓의 캔들스틱 데이터를 조회한다."""

        if count <= 0:
            raise ValueError("count 값은 1 이상이어야 합니다.")
        response = await self._client.get(f"/public/candlestick/{market}/{interval}")
        payload = self._decode_response(response)
        data = payload.get("data")
        if not isinstance(data, list):
            raise BithumbAPIError("invalid", "candlestick 데이터 형식이 올바르지 않습니다.")
        candles = [Candle.from_bithumb_payload(market, entry) for entry in data[-count:]]
        return candles

    async def get_balance(self, currency: str, payment_currency: str = "KRW") -> BalanceSnapshot:
        """특정 코인의 잔고를 조회한다."""

        body = {
            "currency": currency.upper(),
            "payment_currency": payment_currency.upper(),
        }
        payload = await self.private_post("/info/balance", body)
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise BithumbAPIError("invalid", "balance 데이터 형식이 올바르지 않습니다.")
        return BalanceSnapshot.from_payload(currency, data)

    async def place_order(
        self,
        order_currency: str,
        side: OrderSide,
        *,
        units: Decimal,
        price: Decimal,
        payment_currency: str = "KRW",
        **params: Any,
    ) -> OrderExecution:
        """지정가 주문을 생성한다."""

        body: MutableMapping[str, Any] = {
            "order_currency": order_currency.upper(),
            "payment_currency": payment_currency.upper(),
            "type": side.value,
            "units": self._stringify(units),
            "price": self._stringify(price),
        }
        body.update({key: self._stringify(value) for key, value in params.items()})
        payload = await self.private_post("/trade/place", body)
        data = payload.get("data")
        info = data if isinstance(data, Mapping) else {}
        order_id = info.get("order_id") or payload.get("order_id")
        if not order_id:
            raise BithumbAPIError("invalid", "주문 응답에 order_id 가 없습니다.")
        ordered_units = Decimal(str(info.get("units", body["units"])))
        remaining = Decimal(str(info.get("units_remaining", "0")))
        executed = max(Decimal("0"), ordered_units - remaining)
        fee = Decimal(str(info.get("fee", "0")))
        price_value = Decimal(str(info.get("price", body["price"])))
        market = f"{order_currency.upper()}_{payment_currency.upper()}"
        return OrderExecution(
            order_id=str(order_id),
            market=market,
            side=side,
            price=price_value,
            ordered_units=ordered_units,
            executed_units=executed,
            fee=fee,
            created_at=datetime.now(timezone.utc),
        )

    async def cancel_order(
        self,
        order_id: str,
        order_currency: str,
        side: OrderSide,
        payment_currency: str = "KRW",
    ) -> bool:
        """기존 주문을 취소한다."""

        body = {
            "order_id": order_id,
            "order_currency": order_currency.upper(),
            "payment_currency": payment_currency.upper(),
            "type": side.value,
        }
        payload = await self.private_post("/trade/cancel", body)
        return payload.get("status") == "0000"

    async def private_post(self, path: str, body: Optional[Mapping[str, Any]] = None) -> Mapping[str, Any]:
        """인증이 필요한 POST 요청을 전송한다."""

        context = self._prepare_private_request(path, body or {})
        response = await self._client.post(
            context.endpoint,
            data={"endpoint": context.endpoint, **context.body},
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "Api-Key": self._require_api_key(),
                "Api-Sign": context.signature,
                "Api-Nonce": context.nonce,
            },
        )
        return self._decode_response(response)

    def _require_api_key(self) -> str:
        if not self._api_key:
            raise BithumbCredentialsError()
        return self._api_key

    def _require_api_secret(self) -> str:
        if not self._api_secret:
            raise BithumbCredentialsError()
        return self._api_secret

    def _prepare_private_request(self, path: str, body: Mapping[str, Any]) -> _PrivateRequestContext:
        endpoint = self._normalize_endpoint(path)
        nonce = self._nonce_factory()
        stringified_body = {key: self._stringify(value) for key, value in body.items()}
        request_body = {"endpoint": endpoint, **stringified_body}
        encoded_body = urlencode(request_body)
        auth_payload = f"{endpoint}\0{encoded_body}\0{nonce}"
        signature = base64.b64encode(
            hmac.new(
                self._require_api_secret().encode(),
                auth_payload.encode(),
                hashlib.sha512,
            ).digest()
        ).decode()
        return _PrivateRequestContext(endpoint=endpoint, body=body, nonce=nonce, signature=signature)

    def _decode_response(self, response: httpx.Response) -> Mapping[str, Any]:
        response.raise_for_status()
        payload = response.json()
        status = payload.get("status")
        if status and status != "0000":
            raise BithumbAPIError(status, payload.get("message"))
        return payload

    @staticmethod
    def _normalize_endpoint(path: str) -> str:
        if not path:
            raise ValueError("엔드포인트 경로가 비어 있습니다.")
        return path if path.startswith("/") else f"/{path}"

    @staticmethod
    def _default_nonce() -> str:
        return str(int(time.time() * 1000))

    @staticmethod
    def _stringify(value: Any) -> str:
        if isinstance(value, Decimal):
            return format(value, "f")
        return str(value)


__all__ = [
    "BalanceSnapshot",
    "BithumbAPIError",
    "BithumbClient",
    "BithumbCredentialsError",
    "Candle",
    "OrderExecution",
    "OrderSide",
    "Ticker",
]
