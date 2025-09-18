"""빗썸 웹소켓 시세 수집기."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Awaitable, Callable, List, Optional, Sequence

import websockets
from websockets.client import WebSocketClientProtocol

from ..config.settings import AppSettings, get_settings
from ..data import TickerSnapshot
from ..data.repository import TradingRepository

TickerCallback = Callable[[TickerSnapshot], Awaitable[None]]


class BithumbWebsocketCollector:
    """빗썸 티커 스트림을 구독해 저장소에 적재한다."""

    def __init__(
        self,
        markets: Sequence[str],
        *,
        repository: Optional[TradingRepository] = None,
        settings: Optional[AppSettings] = None,
        reconnect_interval: float = 5.0,
    ) -> None:
        self._settings = settings or get_settings()
        self._markets = [market.upper() for market in markets]
        self._repository = repository
        self._callbacks: List[TickerCallback] = []
        self._reconnect_interval = reconnect_interval
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None

    def register_callback(self, callback: TickerCallback) -> None:
        self._callbacks.append(callback)

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task
        self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                async with websockets.connect(self._settings.bithumb_ws_url, ping_interval=30) as websocket:
                    await self._subscribe(websocket)
                    await self._consume(websocket)
            except Exception:  # pragma: no cover - 네트워크 오류 대비
                await asyncio.sleep(self._reconnect_interval)

    async def _subscribe(self, websocket: WebSocketClientProtocol) -> None:
        payload = {
            "type": "ticker",
            "symbols": self._markets,
            "tickTypes": ["24H"],
        }
        await websocket.send(json.dumps(payload))

    async def _consume(self, websocket: WebSocketClientProtocol) -> None:
        async for message in websocket:
            if self._stop_event.is_set():
                break
            snapshot = self._parse_message(message)
            if snapshot is None:
                continue
            if self._repository is not None:
                await self._repository.record_ticker(snapshot)
            for callback in self._callbacks:
                await callback(snapshot)

    def _parse_message(self, message: str) -> Optional[TickerSnapshot]:
        try:
            data = json.loads(message)
        except json.JSONDecodeError:  # pragma: no cover - 방어적 처리
            return None
        if data.get("type") != "ticker":
            return None
        content = data.get("content") or data.get("data")
        if not isinstance(content, dict):
            return None
        market = content.get("symbol") or content.get("market")
        if not isinstance(market, str):
            return None
        price_raw = content.get("closePrice") or content.get("close") or content.get("tradePrice")
        volume_raw = content.get("volume") or content.get("accTradeVolume") or content.get("volume24H")
        change_raw = content.get("chgRate") or content.get("changeRate") or content.get("fluctateRate24H")
        timestamp_raw = content.get("date") or content.get("time") or content.get("timestamp")
        if price_raw is None or volume_raw is None:
            return None
        timestamp = self._parse_timestamp(timestamp_raw)
        price = Decimal(str(price_raw))
        volume = Decimal(str(volume_raw))
        change = Decimal(str(change_raw)) if change_raw is not None else Decimal("0")
        return TickerSnapshot(
            market=market.upper(),
            price=price,
            change_rate_24h=change,
            volume_24h=volume,
            timestamp=timestamp,
        )

    @staticmethod
    def _parse_timestamp(value: object) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value) / 1000 if value > 1e12 else float(value), tz=timezone.utc)
        if isinstance(value, str) and value.isdigit():
            ivalue = int(value)
            return datetime.fromtimestamp(ivalue / 1000 if len(value) > 10 else ivalue, tz=timezone.utc)
        return datetime.now(timezone.utc)


__all__ = ["BithumbWebsocketCollector"]
