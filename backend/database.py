"""数据库连接配置"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# 使用统一路径管理
from backend.utils.paths import DATA_DIR

# 数据库文件路径
DATABASE_PATH = DATA_DIR / "countbot.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_PATH}"
SYNC_DATABASE_URL = f"sqlite:///{DATABASE_PATH}"


class Base(DeclarativeBase):
    """数据库模型基类"""

    pass


# 异步引擎
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

# 同步引擎（用于非异步上下文）
sync_engine = create_engine(
    SYNC_DATABASE_URL,
    echo=False,
    future=True,
)

# 会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# 同步会话工厂
SessionLocal = sessionmaker(
    sync_engine,
    expire_on_commit=False,
)

# 会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# 同步会话工厂
SessionLocal = sessionmaker(
    sync_engine,
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
    from backend.models import CronJob, Message, Personality, Session, Setting, Task, ToolConversation  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 初始化性格数据
    await init_personalities()


async def init_personalities() -> None:
    """初始化内置性格数据（如果表为空）"""
    from backend.models.personality import Personality
    from sqlalchemy import select
    
    async with AsyncSessionLocal() as session:
        try:
            # 检查是否已有数据
            result = await session.execute(select(Personality))
            existing = result.scalars().first()
            
            if existing:
                return  # 已有数据，跳过初始化
            
            # 从 personalities.py 导入内置数据
            from backend.modules.agent.personalities import PERSONALITY_PRESETS
            
            # 图标映射
            icon_map = {
                "grumpy": "CloudLightning",
                "roast": "Frown",
                "gentle": "Heart",
                "blunt": "Target",
                "toxic": "Snowflake",
                "chatty": "MessageSquare",
                "philosopher": "BookOpen",
                "cute": "Smile",
                "humorous": "Laugh",
                "hyper": "TrendingUp",
                "chuuni": "Gamepad2",
                "zen": "Clock",
            }
            
            # 插入内置性格
            for pid, data in PERSONALITY_PRESETS.items():
                personality = Personality(
                    id=pid,
                    name=data["name"],
                    description=data["description"],
                    traits=data["traits"],
                    speaking_style=data["speaking_style"],
                    icon=icon_map.get(pid, "Smile"),
                    is_builtin=True,
                    is_active=True,
                )
                session.add(personality)
            
            await session.commit()
            
        except Exception:
            await session.rollback()
            # 静默失败，不影响数据库初始化
            pass
