"""FastAPI 모니터링 엔드포인트."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Query

from ..data import TradingRepository
from ..runtime.orchestrator import TradingOrchestrator


@dataclass
class ApplicationContext:
    orchestrator: TradingOrchestrator
    repository: TradingRepository


def create_app(context: ApplicationContext) -> FastAPI:
    app = FastAPI(title="Beombong Trading API", version="0.1.0")
    app.state.context = context

    def get_context() -> ApplicationContext:
        return app.state.context

    @app.on_event("startup")
    async def _startup() -> None:  # pragma: no cover - FastAPI 훅
        context.orchestrator.start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:  # pragma: no cover - FastAPI 훅
        await context.orchestrator.shutdown()

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/status")
    async def status(ctx: ApplicationContext = Depends(get_context)) -> Dict[str, Any]:
        return ctx.orchestrator.status()

    @app.post("/pause")
    async def pause(ctx: ApplicationContext = Depends(get_context)) -> Dict[str, str]:
        ctx.orchestrator.pause()
        return {"status": "paused"}

    @app.post("/resume")
    async def resume(ctx: ApplicationContext = Depends(get_context)) -> Dict[str, str]:
        ctx.orchestrator.resume()
        return {"status": "running"}

    @app.get("/cycles")
    async def recent_cycles(
        ctx: ApplicationContext = Depends(get_context),
        limit: int = Query(20, ge=1, le=100),
    ) -> Dict[str, Any]:
        cycles = await ctx.repository.recent_cycles(limit)
        return {"items": cycles}

    @app.get("/performance/daily")
    async def daily_performance(
        ctx: ApplicationContext = Depends(get_context),
        target: Optional[date] = Query(None, description="기준 일자 (YYYY-MM-DD)"),
    ) -> Dict[str, Any]:
        target_date = target or datetime.utcnow().date()
        performance = await ctx.repository.daily_performance(target_date)
        return {
            "date": performance.trade_date.isoformat(),
            "realized_pnl": str(performance.realized_pnl),
            "trade_count": performance.trade_count,
            "winning_trades": performance.winning_trades,
            "losing_trades": performance.losing_trades,
            "best_trade": str(performance.best_trade) if performance.best_trade is not None else None,
            "worst_trade": str(performance.worst_trade) if performance.worst_trade is not None else None,
        }

    return app


__all__ = ["ApplicationContext", "create_app"]
