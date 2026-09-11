from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings


class Base(DeclarativeBase):
    pass


kwargs = {"echo": False}
if "sqlite" not in settings.DATABASE_URL:
    kwargs.update({
        "pool_size": 2,
        "max_overflow": 2,
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_timeout": 10,
        "connect_args": {"timeout": 10, "command_timeout": 30},
    })
else:
    kwargs["connect_args"] = {"timeout": 15}

engine = create_async_engine(settings.DATABASE_URL, **kwargs)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
