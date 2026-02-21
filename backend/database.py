"""数据库连接配置"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# 数据目录
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# 数据库文件路径
DATABASE_PATH = DATA_DIR / "countbot.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_PATH}"


class Base(DeclarativeBase):
    """数据库模型基类"""

    pass


# 异步引擎
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

# 会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """获取数据库会话"""
    async with AsyncSessionLocal() as session:
        yield session


def get_db_session_factory():
    """获取数据库会话工厂
    
    用于需要创建多个独立会话的场景，如 Cron 调度器
    """
    return AsyncSessionLocal


async def init_db() -> None:
    """初始化数据库"""
    # 导入所有模型以确保表被创建
    from backend.models import CronJob, Message, Session, Setting, Task, ToolConversation  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
