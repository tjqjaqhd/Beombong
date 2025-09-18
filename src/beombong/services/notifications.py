"""알림 채널 모듈."""

from __future__ import annotations

from typing import Any, Optional, Sequence

import httpx


class SlackNotifier:
    """Slack Webhook 으로 메시지를 전송한다."""

    def __init__(self, webhook_url: Optional[str], *, client: Optional[httpx.AsyncClient] = None) -> None:
        self._webhook_url = webhook_url
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def send(self, text: str, *, blocks: Optional[Sequence[dict[str, Any]]] = None) -> None:
        if not self._webhook_url:
            return
        payload: dict[str, Any] = {"text": text}
        if blocks:
            payload["blocks"] = list(blocks)
        response = await self._client.post(self._webhook_url, json=payload)
        response.raise_for_status()


__all__ = ["SlackNotifier"]
