"""SQLAlchemy 비동기 엔진 및 세션 유틸리티."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """프로젝트 전역에서 공유하는 Declarative Base."""


async_session_factory = async_sessionmaker[AsyncSession]


def create_engine(database_url: str) -> AsyncEngine:
    """주어진 URL 로 비동기 SQLAlchemy 엔진을 생성한다."""

    return create_async_engine(database_url, future=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """비동기 세션 팩토리를 생성한다."""

    return async_sessionmaker(engine, expire_on_commit=False)


async def init_models(engine: AsyncEngine) -> None:
    """모든 테이블을 생성한다."""

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


__all__ = ["Base", "create_engine", "create_session_factory", "init_models"]
