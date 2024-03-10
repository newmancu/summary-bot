from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)

from summary_bot.config import get_settings

engine = create_async_engine(
    get_settings().db.db_url, future=True, echo=get_settings().debug
)
async_session = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
