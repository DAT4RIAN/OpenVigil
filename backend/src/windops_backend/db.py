from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

# Import mapped storage entities so test-only metadata bootstrap includes them.
from windops_backend import storage as _storage  # noqa: F401
from windops_backend.config import Settings
from windops_backend.models import Base


def create_engine(settings: Settings) -> AsyncEngine:
    kwargs: dict[str, object] = {"pool_pre_ping": True}
    if settings.is_sqlite and settings.database_url.endswith(":memory:"):
        kwargs.update({"poolclass": StaticPool, "connect_args": {"check_same_thread": False}})
    return create_async_engine(settings.database_url, **kwargs)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    return factory


async def bootstrap_schema(engine: AsyncEngine, settings: Settings) -> None:
    if not settings.schema_bootstrap:
        return
    if settings.environment.value != "test":
        raise RuntimeError("schema_bootstrap is test-only; use Alembic elsewhere")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
