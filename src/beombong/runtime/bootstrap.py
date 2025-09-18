"""런타임 구성과 FastAPI 애플리케이션 부트스트랩."""

from __future__ import annotations

from ..api.app import ApplicationContext, create_app
from ..clients.bithumb import BithumbClient
from ..clients.bithumb_ws import BithumbWebsocketCollector
from ..config.settings import get_settings
from ..data.database import create_engine, create_session_factory, init_models
from ..data.repository import TradingRepository
from ..services.notifications import SlackNotifier
from ..services.portfolio import PortfolioState
from ..services.reporting import PerformanceReporter
from ..services.trading import RiskParameters, TradingEngine
from ..strategies.momentum_breakout import MomentumBreakoutStrategy


async def build_application() -> "FastAPI":
    settings = get_settings()
    engine = create_engine(str(settings.database_url))
    await init_models(engine)
    session_factory = create_session_factory(engine)
    repository = TradingRepository(session_factory)
    reporter = PerformanceReporter(repository)
    notifier = SlackNotifier(settings.slack_webhook_url)

    client = BithumbClient(settings=settings)
    portfolio = PortfolioState()
    strategy = MomentumBreakoutStrategy()
    risk = RiskParameters(
        max_allocation_pct=settings.max_allocation_pct,
        min_cash_reserve_pct=settings.min_cash_reserve_pct,
        min_order_value=settings.min_order_value,
        max_order_value=settings.max_order_value,
        daily_loss_limit_pct=settings.daily_loss_limit_pct,
        daily_loss_limit_value=settings.daily_loss_limit_value,
        max_consecutive_losses=settings.max_consecutive_losses,
        order_retry_limit=settings.order_retry_limit,
        order_retry_delay=settings.order_retry_delay,
    )
    trading_engine = TradingEngine(
        client=client,
        strategy=strategy,
        portfolio=portfolio,
        market=settings.trading_market,
        candle_interval=settings.candle_interval,
        candle_count=settings.candle_count,
        risk=risk,
    )

    from .orchestrator import TradingOrchestrator  # 지연 임포트로 순환 방지

    orchestrator = TradingOrchestrator(
        engine=trading_engine,
        repository=repository,
        notifier=notifier,
        reporter=reporter,
        settings=settings,
    )

    context = ApplicationContext(orchestrator=orchestrator, repository=repository)
    app = create_app(context)

    if settings.websocket_enabled:
        collector = BithumbWebsocketCollector([settings.trading_market], repository=repository, settings=settings)

        @app.on_event("startup")
        async def _start_ws() -> None:  # pragma: no cover - FastAPI 훅
            await collector.start()

        @app.on_event("shutdown")
        async def _stop_ws() -> None:  # pragma: no cover - FastAPI 훅
            await collector.stop()

    @app.on_event("shutdown")
    async def _close_client() -> None:  # pragma: no cover - FastAPI 훅
        await client.aclose()

    return app


__all__ = ["build_application"]
