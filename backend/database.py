"""数据库连接配置"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Tuple

from loguru import logger
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# 使用统一路径管理
from backend.utils.paths import DATA_DIR

# 数据库文件路径
DATABASE_PATH = DATA_DIR / "countbot.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_PATH}"
SYNC_DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# ======================================================================
# SQLite 并发参数
#
# 默认的 rollback journal 模式下，一个读事务（SHARED 锁）就会挡住所有写操作；
# 而本项目的对话/定时任务会在流式响应期间长时间持有请求级 DB 会话，
# 一旦期间有读事务未结束，其它写请求全部报 "database is locked"（且长时间不恢复）。
# 因此统一改用 WAL：读不挡写、写不挡读；再给每个连接加 busy_timeout，
# 把短暂的写-写竞争变成「等待重试」而不是直接失败。
# ======================================================================

SQLITE_JOURNAL_MODE = "WAL"
SQLITE_BUSY_TIMEOUT_MS = 15000
SQLITE_SYNCHRONOUS = "NORMAL"
_SQLITE_PRAGMAS: Tuple[str, ...] = (
    f"PRAGMA journal_mode={SQLITE_JOURNAL_MODE}",
    f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}",
    f"PRAGMA synchronous={SQLITE_SYNCHRONOUS}",
)


def _apply_sqlite_pragmas(dbapi_connection: Any, _record: Any = None) -> None:
    """在每次新建连接时应用 PRAGMA（busy_timeout 是连接级，必须逐连接设置）。"""
    cursor = dbapi_connection.cursor()
    try:
        for pragma in _SQLITE_PRAGMAS:
            cursor.execute(pragma)
    finally:
        cursor.close()


def register_sqlite_pragmas(engine: Any) -> None:
    """把 PRAGMA 注册到引擎（sync 引擎直接挂；async 引擎挂到其 sync_engine）。"""
    target = getattr(engine, "sync_engine", engine)
    event.listen(target, "connect", _apply_sqlite_pragmas)


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
            CompatibilityColumnMigration(
                name="short_context_summary",
                ddl="short_context_summary TEXT",
            ),
            CompatibilityColumnMigration(
                name="short_context_summary_msg_id",
                ddl="short_context_summary_msg_id INTEGER",
            ),
            CompatibilityColumnMigration(
                name="short_context_summary_updated_at",
                ddl="short_context_summary_updated_at DATETIME",
            ),
            CompatibilityColumnMigration(
                name="short_context_summary_window_size",
                ddl="short_context_summary_window_size INTEGER",
            ),
            CompatibilityColumnMigration(
                name="auto_memory_summary_msg_id",
                ddl="auto_memory_summary_msg_id INTEGER",
            ),
            # 会话级工作空间：旧会话留空，继续跟随全局配置。
            CompatibilityColumnMigration(
                name="workspace_path",
                ddl="workspace_path TEXT",
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
    CompatibilityTableMigration(
        table_name="cron_jobs",
        columns=(
            CompatibilityColumnMigration(
                name="account_id",
                ddl="account_id VARCHAR",
            ),
            # 定时任务可指定模型；旧行留空即跟随全局默认模型。
            CompatibilityColumnMigration(
                name="model_provider",
                ddl="model_provider VARCHAR",
            ),
            CompatibilityColumnMigration(
                name="model_name",
                ddl="model_name VARCHAR",
            ),
        ),
    ),
    CompatibilityTableMigration(
        table_name="tool_conversations",
        # 旧行不回填：读者只在该列含完整 kind/version 时按 canonical 投影解释。
        columns=(CompatibilityColumnMigration("outcome_projection", "outcome_projection TEXT"),),
    ),
    CompatibilityTableMigration(
        table_name="tasks",
        # 与 ToolConversation 一样只加 nullable 列，保持旧任务记录可读。
        columns=(CompatibilityColumnMigration("outcome_projection", "outcome_projection TEXT"),),
    ),
)


# 异步引擎
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)
register_sqlite_pragmas(engine)

# 同步引擎（用于非异步上下文）
sync_engine = create_engine(
    SYNC_DATABASE_URL,
    echo=False,
    future=True,
)
register_sqlite_pragmas(sync_engine)

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
