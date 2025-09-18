"""애플리케이션 설정 로더."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import AnyUrl, Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

from decimal import Decimal
from datetime import time


class AppSettings(BaseSettings):
    """환경 변수 기반 프로젝트 설정."""

    model_config = SettingsConfigDict(
        env_prefix="BEOMBONG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bithumb_base_url: HttpUrl = Field(
        default="https://api.bithumb.com",
        description="빗썸 Open API 기본 URL",
    )
    bithumb_api_key: Optional[str] = Field(
        default=None,
        description="빗썸 Open API Key",
    )
    bithumb_api_secret: Optional[str] = Field(
        default=None,
        description="빗썸 Open API Secret",
    )
    http_timeout: float = Field(
        default=10.0,
        description="HTTP 요청 타임아웃(초)",
        ge=0.1,
    )
    database_url: AnyUrl = Field(
        default="sqlite+aiosqlite:///./beombong.db",
        description="SQLAlchemy 호환 데이터베이스 URL",
    )
    scheduler_timezone: str = Field(
        default="Asia/Seoul",
        description="트레이딩/리포트 스케줄러에 사용할 타임존",
    )
    trading_market: str = Field(
        default="BTC_KRW",
        description="자동매매를 수행할 마켓 코드",
    )
    trading_interval_seconds: int = Field(
        default=300,
        description="트레이딩 사이클 실행 간격(초)",
        ge=30,
    )
    candle_interval: str = Field(
        default="1h",
        description="전략 평가에 사용할 캔들 간격",
    )
    candle_count: int = Field(
        default=120,
        description="전략 평가를 위한 캔들 조회 개수",
        ge=20,
    )
    slack_webhook_url: Optional[HttpUrl] = Field(
        default=None,
        description="Slack Webhook URL (선택)",
    )
    daily_report_time: time = Field(
        default=time(8, 30),
        description="일일 성과 리포트를 전송할 시각(HH:MM)",
    )
    websocket_enabled: bool = Field(
        default=True,
        description="웹소켓 시세 수집 활성화 여부",
    )
    bithumb_ws_url: AnyUrl = Field(
        default="wss://pubwss.bithumb.com/pub/ws",
        description="빗썸 웹소켓 엔드포인트",
    )
    max_allocation_pct: Decimal = Field(
        default=Decimal("0.3"),
        description="단일 주문에 허용되는 최대 현금 비중",
        ge=Decimal("0"),
        le=Decimal("1"),
    )
    min_cash_reserve_pct: Decimal = Field(
        default=Decimal("0.1"),
        description="항상 남겨둘 최소 현금 비중",
        ge=Decimal("0"),
        lt=Decimal("1"),
    )
    min_order_value: Decimal = Field(
        default=Decimal("5000"),
        description="주문 최소 금액",
        ge=Decimal("0"),
    )
    max_order_value: Optional[Decimal] = Field(
        default=None,
        description="주문 최대 금액 (없으면 무제한)",
        ge=Decimal("0"),
    )
    daily_loss_limit_pct: Decimal = Field(
        default=Decimal("0.05"),
        description="일일 손실 한도 비율",
        ge=Decimal("0"),
    )
    daily_loss_limit_value: Optional[Decimal] = Field(
        default=None,
        description="일일 손실 한도 금액",
    )
    max_consecutive_losses: int = Field(
        default=3,
        description="연속 손실 허용 횟수",
        ge=0,
    )
    order_retry_limit: int = Field(
        default=2,
        description="주문 실패 시 재시도 횟수",
        ge=0,
    )
    order_retry_delay: float = Field(
        default=1.5,
        description="주문 재시도 간 대기 시간(초)",
        ge=0.0,
    )
    api_host: str = Field(
        default="0.0.0.0",
        description="FastAPI 서버 호스트",
    )
    api_port: int = Field(
        default=8000,
        description="FastAPI 서버 포트",
        ge=1,
        le=65535,
    )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """싱글턴 형태로 설정을 반환한다."""

    return AppSettings()


__all__ = ["AppSettings", "get_settings"]
