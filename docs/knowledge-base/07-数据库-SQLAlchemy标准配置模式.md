# SQLAlchemy 标准配置模式

CountBot 的 `backend/database.py` 中使用了 SQLAlchemy 的标准配置模式。本文以 Q&A 形式逐一讲解这些模式，帮助理解"为什么要这样写"。

## 1、数据库连接 URL 是什么格式？

```python
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_PATH}"
SYNC_DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
```

SQLAlchemy 的连接 URL 遵循统一格式：

```
dialect+driver://username:password@host:port/database
```

各部分含义：

| 部分 | 说明 | 示例 |
|------|------|------|
| dialect | 数据库类型 | `sqlite`、`mysql`、`postgresql` |
| driver | Python 驱动库 | `aiosqlite`（异步）、`pymysql`、`psycopg2` |
| username:password | 认证信息 | SQLite 不需要 |
| host:port | 服务器地址 | SQLite 不需要（是本地文件） |
| database | 数据库名/路径 | `/path/to/countbot.db` |

### （1）为什么有两个 URL？

```python
# 异步 URL — 用 aiosqlite 驱动
"sqlite+aiosqlite:///path/to/db"

# 同步 URL — 用 sqlite3 内置驱动（不写 driver 部分）
"sqlite:///path/to/db"
```

异步引擎需要异步驱动（`aiosqlite`），同步引擎用默认驱动（Python 内置的 `sqlite3`）。两个 URL 指向同一个数据库文件，只是访问方式不同。

### （2）三个斜杠 `///` 是什么意思？

`sqlite:///path` 中的三个斜杠：前两个是协议分隔符 `://`，第三个是绝对路径的开头 `/`。如果是相对路径，就只有两个斜杠后跟路径：`sqlite://relative/path`。

## 2、Base 基类是什么？

```python
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """数据库模型基类"""
    pass
```

### （1）DeclarativeBase 做了什么？

`DeclarativeBase` 是 SQLAlchemy 2.0 引入的声明式基类。继承它的类会自动获得：

- **元数据注册**：`Base.metadata` 记录了所有表的结构信息
- **ORM 映射能力**：子类可以用 Python 类属性定义数据库列

```python
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String)
```

### （2）为什么 Base 类本身是空的？

`Base` 只是一个"注册中心"，它的作用是把所有继承它的模型类关联到同一个 `metadata`。后续调用 `Base.metadata.create_all()` 时，SQLAlchemy 就知道要创建哪些表。

### （3）旧版写法对比

```python
# SQLAlchemy 1.x 旧写法
from sqlalchemy.ext.declarative import declarative_base
Base = declarative_base()

# SQLAlchemy 2.0 新写法（本项目使用）
from sqlalchemy.orm import DeclarativeBase
class Base(DeclarativeBase):
    pass
```

新写法的好处是支持类型检查（mypy / pyright），IDE 补全更好。

## 3、引擎（Engine）是什么？

```python
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import create_engine

# 异步引擎
engine = create_async_engine(DATABASE_URL, echo=False, future=True)

# 同步引擎
sync_engine = create_engine(SYNC_DATABASE_URL, echo=False, future=True)
```

### （1）引擎的角色

引擎是**数据库连接的管理者**，负责：

- 维护一个**连接池**（不用每次查询都新建连接）
- 管理数据库驱动
- 提供执行 SQL 的底层接口

可以类比为"数据库连接的工厂"——你不直接操作连接，而是通过引擎来获取和管理连接。

### （2）参数说明

| 参数 | 值 | 说明 |
|------|---|------|
| `echo` | `False` | 是否在控制台打印所有 SQL 语句（调试时可设为 `True`） |
| `future` | `True` | 使用 SQLAlchemy 2.0 风格 API（向前兼容） |

### （3）为什么需要同步引擎和异步引擎？

项目主体是异步的（FastAPI），所以主要用异步引擎。但某些场景无法使用异步（比如在同步回调、Alembic 迁移脚本中），就需要同步引擎作为补充。两个引擎连接同一个数据库文件，只是访问方式不同。

## 4、会话工厂（Session Factory）是什么？

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker

# 异步会话工厂
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
```

### （1）为什么用工厂而不是直接创建会话？

工厂模式的好处是**把配置和创建分开**：

```python
# 不用工厂 — 每次都要写一堆参数
session1 = AsyncSession(engine, expire_on_commit=False)
session2 = AsyncSession(engine, expire_on_commit=False)

# 用工厂 — 配置一次，后续调用很简洁
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
session1 = AsyncSessionLocal()
session2 = AsyncSessionLocal()
```

配置只写一次，后面每次 `AsyncSessionLocal()` 就能得到一个配置好的会话实例。

### （2）Session 是什么？

Session（会话）是**与数据库交互的工作区**，负责：

- 执行查询和写入操作
- 跟踪对象的变更（脏检查）
- 管理事务（commit / rollback）

一个 Session 通常对应一次"业务操作"（比如处理一个 HTTP 请求）。

### （3）expire_on_commit=False 是什么意思？

默认情况下，`commit()` 之后 Session 会将所有对象标记为"过期"，下次访问属性时会重新查询数据库。设置 `expire_on_commit=False` 后，`commit()` 之后对象的属性仍然可用，不会触发额外查询。

```python
# expire_on_commit=True（默认）
await session.commit()
print(user.name)  # 触发一次 SELECT 查询来刷新数据

# expire_on_commit=False（本项目设置）
await session.commit()
print(user.name)  # 直接返回内存中的值，不查询
```

在异步环境中，这个设置尤其重要——如果在 `await session.commit()` 之后、Session 关闭之后访问对象属性，默认行为会尝试用已关闭的连接查询，导致报错。

### （4）class_=AsyncSession 是什么？

告诉工厂"创建会话时，请使用 `AsyncSession` 类型"。`AsyncSession` 是 `Session` 的异步版本，所有数据库操作都返回协程，需要 `await`。

## 5、get_db() 依赖注入是什么模式？

```python
async def get_db() -> AsyncSession:
    """获取数据库会话"""
    async with AsyncSessionLocal() as session:
        yield session
```

### （1）这个函数做了什么？

1. 创建一个异步会话（`AsyncSessionLocal()`）
2. 通过 `yield` 把会话交给调用者使用
3. 调用者用完后，`async with` 自动关闭会话

### （2）为什么用 yield 而不是 return？

这是 FastAPI 的**依赖注入**模式。用 `yield` 可以在请求处理完成后执行清理操作：

```python
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session          # ← 请求处理期间，调用者使用这个 session
    # ← async with 退出，session 自动关闭（清理）
```

FastAPI 会自动识别带 `yield` 的依赖，在请求结束后执行 `yield` 之后的代码（这里是 `async with` 的退出清理）。

### （3）在 FastAPI 中怎么使用？

```python
from fastapi import Depends

@app.get("/users")
async def get_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    return result.scalars().all()
```

每个请求都会自动获得一个独立的数据库会话，请求结束后自动关闭。

## 6、get_db_session_factory() 是做什么的？

```python
def get_db_session_factory():
    """获取数据库会话工厂"""
    return AsyncSessionLocal
```

### （1）为什么需要这个函数？

`get_db()` 通过 `yield` 提供单个会话，适合"一个请求一个会话"的场景。但有些场景需要**自己控制会话的创建**，比如 Cron 定时任务调度器——它不在 HTTP 请求上下文中，需要在任务执行时自己创建和管理会话。

```python
# Cron 调度器的用法
factory = get_db_session_factory()

async def run_cron_job():
    async with factory() as session:  # 自己创建会话
        # 执行定时任务...
        await session.commit()
```

### （2）为什么不直接 import AsyncSessionLocal？

通过函数封装，可以在不改调用方代码的情况下切换实现（比如测试时替换为内存数据库的工厂）。这是一种松耦合的设计。

## 7、init_db() 建表模式是什么？

```python
async def init_db() -> None:
    """初始化数据库"""
    from backend.models import CronJob, Message, Personality, Session, Setting, Task, ToolConversation

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await init_personalities()
```

### （1）为什么在函数内部 import 模型？

这是**延迟导入**模式。模型类在被 import 时会自动注册到 `Base.metadata`。在 `init_db()` 内部导入，确保调用 `create_all()` 时所有模型已注册。

如果在文件顶部导入，可能因为循环依赖导致问题。

### （2）engine.begin() 是什么？

`engine.begin()` 开启一个数据库连接并自动管理事务：

```python
async with engine.begin() as conn:
    # 在事务中执行操作
    await conn.run_sync(Base.metadata.create_all)
# 正常退出 → 自动 commit
# 异常退出 → 自动 rollback
```

### （3）run_sync 是什么？

`Base.metadata.create_all()` 是一个同步方法（SQLAlchemy 的元数据 API 不支持异步）。`conn.run_sync()` 的作用是在异步上下文中安全地调用同步方法：

```python
# 不能这样写（create_all 是同步的，会阻塞事件循环）
Base.metadata.create_all(conn)

# 正确写法 — run_sync 把同步调用放到线程池中执行
await conn.run_sync(Base.metadata.create_all)
```

`run_sync` 内部会在线程池中执行同步函数，不阻塞事件循环。

## 8、整体架构图

```
database.py 的对象关系：

┌─────────────────────────────────────────────┐
│              数据库文件                        │
│          countbot.db                         │
└──────────┬────────────────────┬──────────────┘
           │                    │
    ┌──────┴──────┐      ┌─────┴──────┐
    │  异步引擎    │      │  同步引擎   │
    │  engine     │      │  sync_engine│
    └──────┬──────┘      └─────┬──────┘
           │                    │
    ┌──────┴──────────┐  ┌─────┴──────────┐
    │ AsyncSessionLocal│  │  SessionLocal  │
    │  (异步会话工厂)  │  │  (同步会话工厂) │
    └──────┬──────────┘  └────────────────┘
           │
    ┌──────┴──────────────────────────┐
    │                                  │
    ▼                                  ▼
get_db()                    get_db_session_factory()
(FastAPI 依赖注入)           (Cron 等自管理场景)
```

## 9、常见 Q&A

### （1）能不能只用异步引擎，不要同步引擎？

理论上可以，但实际中有些场景必须用同步：
- Alembic 数据库迁移默认是同步的
- 某些第三方库只支持同步调用
- `run_sync` 桥接虽然方便，但不是所有操作都能桥接

保留同步引擎是一种务实的做法。

### （2）Base 可以定义公共字段吗？

可以。比如让所有表都有 `created_at` 和 `updated_at`：

```python
class Base(DeclarativeBase):
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
```

本项目保持 `Base` 为空，各模型各自定义字段。

### （3）Session 和 Connection 有什么区别？

- **Connection**：底层数据库连接，直接执行 SQL
- **Session**：高层 ORM 接口，跟踪对象状态，管理事务

日常开发中，绑大多数情况使用 Session。只有在需要直接执行 DDL（如建表）或原始 SQL 时才用 Connection。
