from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from core.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)

async_session_maker = None  # type: async_sessionmaker | None


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session_maker() as session:
        yield session


async def init_db():
    global async_session_maker
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        from models import user, startup, deal, support  # noqa — register all models
        await conn.run_sync(Base.metadata.create_all)
