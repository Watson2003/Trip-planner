from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models.trip import Base
from utils.config import settings


engine = create_async_engine(settings.database_url, echo=False, future=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

