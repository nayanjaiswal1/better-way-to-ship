"""Pytest fixtures shared across all test modules."""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Use test settings before importing app modules
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test_db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("LOG_JSON", "false")

from app.db.base import Base  # noqa: E402
from app.dependencies.db import get_db  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncGenerator[object, None]:
    """Create all tables once per test session, drop them after."""
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: object) -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional session that rolls back after each test."""
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

    async with db_engine.connect() as conn:  # type: ignore[union-attr]
        async with conn.begin():
            session = AsyncSession(bind=conn, expire_on_commit=False)
            yield session
            await session.close()
            await conn.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client with DB session overridden to use the test transaction."""
    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac
