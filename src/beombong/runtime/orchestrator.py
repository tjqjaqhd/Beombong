"""트레이딩 오케스트레이션과 스케줄러."""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..config.settings import AppSettings, get_settings
from ..data import TradingCycleResult
from ..data.repository import TradingRepository
from ..services.notifications import SlackNotifier
from ..services.reporting import PerformanceReporter
from ..services.trading import TradingEngine


class TradingOrchestrator:
    """트레이딩 엔진을 주기적으로 실행하고 결과를 관리한다."""

    def __init__(
        self,
        engine: TradingEngine,
        repository: TradingRepository,
        notifier: SlackNotifier,
        reporter: PerformanceReporter,
        *,
        settings: Optional[AppSettings] = None,
    ) -> None:
        self._engine = engine
        self._repository = repository
        self._notifier = notifier
        self._reporter = reporter
        self._settings = settings or get_settings()
        self._timezone = ZoneInfo(self._settings.scheduler_timezone)
        self._scheduler = AsyncIOScheduler(timezone=self._timezone)
        self._interval_seconds = self._settings.trading_interval_seconds
        self._lock = asyncio.Lock()
        self._running = False
        self._last_result: Optional[TradingCycleResult] = None
        self._last_error: Optional[str] = None

    def start(self) -> None:
        if self._running:
            return
        self._scheduler.add_job(
            self._schedule_cycle,
            IntervalTrigger(seconds=self._interval_seconds, timezone=self._timezone),
            next_run_time=datetime.now(self._timezone),
        )
        report_time = self._settings.daily_report_time
        self._scheduler.add_job(
            self._send_daily_report,
            CronTrigger(hour=report_time.hour, minute=report_time.minute, timezone=self._timezone),
        )
        self._scheduler.start()
        self._running = True

    async def shutdown(self) -> None:
        if not self._running:
            return
        self._scheduler.shutdown(wait=False)
        self._running = False
        await self._notifier.aclose()

    def pause(self) -> None:
        self._scheduler.pause()

    def resume(self) -> None:
        self._scheduler.resume()

    def is_running(self) -> bool:
        return self._running and self._scheduler.state == self._scheduler.STATE_RUNNING

    def _schedule_cycle(self) -> None:
        asyncio.create_task(self._execute_cycle())

    async def _execute_cycle(self) -> None:
        async with self._lock:
            try:
                result = await self._engine.run_cycle()
                self._last_result = result
                self._last_error = None
                await self._repository.record_cycle(result)
                await self._notify_result(result)
            except Exception as exc:  # pragma: no cover - 런타임 안전장치
                self._last_error = str(exc)
                await self._notifier.send(f"트레이딩 사이클 실패: {exc}")

    async def _notify_result(self, result: TradingCycleResult) -> None:
        if result.error:
            await self._notifier.send(f"주문 실패: {result.error}")
            return
        if result.execution is None:
            if result.signal.action.value == "hold":
                return
            await self._notifier.send(f"주문 미실행: {result.signal.reason}")
            return
        execution = result.execution
        side = "매수" if execution.side.is_buy else "매도"
        pnl_text = ""
        if result.pnl != Decimal("0"):
            pnl_text = f" / 실현손익 {result.pnl:.0f} KRW"
        await self._notifier.send(
            f"{execution.market} {side} {execution.executed_units} @ {execution.price} KRW{pnl_text}"
        )

    async def _send_daily_report(self) -> None:
        today = datetime.now(self._timezone).date()
        report = await self._reporter.generate(today)
        await self._notifier.send(
            "일일 성과 리포트",
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": report.format_markdown()}}],
        )

    def status(self) -> dict[str, object]:
        result = self._last_result
        return {
            "running": self.is_running(),
            "last_result": self._format_result(result),
            "risk": self._engine.risk_status(),
            "last_error": self._last_error,
        }

    def _format_result(self, result: Optional[TradingCycleResult]) -> Optional[dict[str, object]]:
        if result is None:
            return None
        return {
            "market": result.signal.market,
            "action": result.signal.action.value,
            "price": str(result.signal.price),
            "timestamp": result.signal.timestamp.isoformat(),
            "status": "error" if result.error else ("executed" if result.execution else "skipped"),
            "pnl": str(result.pnl),
            "error": result.error,
            "notes": result.notes,
        }


__all__ = ["TradingOrchestrator"]
