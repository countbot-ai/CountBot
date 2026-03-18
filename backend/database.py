"""数据库连接配置"""

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from loguru import logger
from sqlalchemy import create_engine, inspect
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


@dataclass(frozen=True)
class CompatibilityColumnMigration:
    """单列兼容迁移定义。"""

    name: str
    ddl: str


@dataclass(frozen=True)
class CompatibilityTableMigration:
    """单表兼容迁移定义。"""

    table_name: str
    columns: Tuple[CompatibilityColumnMigration, ...]


_SCHEMA_COMPATIBILITY_MIGRATIONS = (
    CompatibilityTableMigration(
        table_name="sessions",
        columns=(
            CompatibilityColumnMigration(
                name="session_model_config",
                ddl="session_model_config TEXT",
            ),
            CompatibilityColumnMigration(
                name="session_persona_config",
                ddl="session_persona_config TEXT",
            ),
            CompatibilityColumnMigration(
                name="use_custom_config",
                ddl="use_custom_config BOOLEAN DEFAULT 0",
            ),
            CompatibilityColumnMigration(
                name="channel_context",
                ddl="channel_context TEXT",
            ),
        ),
    ),
    CompatibilityTableMigration(
        table_name="agent_teams",
        columns=(
            CompatibilityColumnMigration(
                name="team_model_config",
                ddl="team_model_config TEXT",
            ),
            CompatibilityColumnMigration(
                name="use_custom_model",
                ddl="use_custom_model BOOLEAN DEFAULT 0",
            ),
        ),
    ),
    CompatibilityTableMigration(
        table_name="messages",
        columns=(
            CompatibilityColumnMigration(
                name="message_context",
                ddl="message_context TEXT",
            ),
        ),
    ),
)


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


def _apply_schema_compatibility_migrations(
    sync_conn,
    migrations: Tuple[CompatibilityTableMigration, ...] = _SCHEMA_COMPATIBILITY_MIGRATIONS,
) -> None:
    """对旧版本数据库执行最小 schema 兼容迁移。"""
    inspector = inspect(sync_conn)
    table_names = set(inspector.get_table_names())

    for table_migration in migrations:
        if table_migration.table_name not in table_names:
            continue

        existing_columns = {
            column["name"]
            for column in inspector.get_columns(table_migration.table_name)
        }

        for column_migration in table_migration.columns:
            if column_migration.name in existing_columns:
                continue

            sync_conn.exec_driver_sql(
                f"ALTER TABLE {table_migration.table_name} ADD COLUMN {column_migration.ddl}"
            )
            logger.warning(
                "Applied compatibility migration for "
                f"{table_migration.table_name}.{column_migration.name}"
            )
            existing_columns.add(column_migration.name)


async def init_db() -> None:
    """初始化数据库"""
    # 导入所有模型以确保表被创建
    from backend.models import AgentTeam, CronJob, Message, Personality, Session, Setting, Task, ToolConversation  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_schema_compatibility_migrations)
    
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

