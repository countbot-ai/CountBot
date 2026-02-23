# FastAPI Lifespan 生命周期管理

## 1、什么是 Lifespan

Lifespan 是 FastAPI 提供的一种机制，用于在**应用启动时初始化资源**、在**应用关闭时清理资源**。

## 2、基本用法

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ===== 应用启动时执行（yield 之前）=====
    print("应用启动，初始化资源...")
    db = await connect_database()

    yield  # 应用在此处运行，处理请求

    # ===== 应用关闭时执行（yield 之后）=====
    print("应用关闭，清理资源...")
    await db.close()

app = FastAPI(lifespan=lifespan)
```

## 3、执行流程

```
应用启动
    ↓
执行 yield 之前的代码（初始化数据库、加载配置等）
    ↓
yield —— 应用正常运行，处理 HTTP 请求
    ↓
执行 yield 之后的代码（关闭连接、释放资源等）
    ↓
应用退出
```

## 4、@asynccontextmanager 装饰器

`@asynccontextmanager` 来自 Python 标准库 `contextlib`，作用是把一个**异步生成器函数**转换为**异步上下文管理器**（可以用 `async with` 的对象）。

没有这个装饰器的话，你需要写一个类来实现 `__aenter__` 和 `__aexit__` 方法，代码会更冗长。

### （1）对比

不用装饰器（繁琐写法）：

```python
class Lifespan:
    async def __aenter__(self):
        # 启动逻辑
        pass

    async def __aexit__(self, *args):
        # 关闭逻辑
        pass
```

用装饰器（简洁写法）：

```python
@asynccontextmanager
async def lifespan(app):
    # 启动逻辑
    yield
    # 关闭逻辑
```

## 5、本项目中的用法

在 `backend/app.py` 中，lifespan 函数做了以下事情：

**启动时（yield 之前）：**
- 初始化数据库
- 加载配置文件
- 创建共享组件（消息队列、限流器等）
- 注册工具、启动频道管理器、启动定时任务调度器

**关闭时（yield 之后）：**
- 停止所有频道
- 停止调度器
- 输出关闭日志

## 6、为什么不用 @app.on_event

旧版 FastAPI 用 `@app.on_event("startup")` 和 `@app.on_event("shutdown")`，但这种写法已被废弃。Lifespan 方式更好，因为：

1. 启动和关闭逻辑写在一个函数里，上下文更清晰
2. 可以方便地共享变量（启动时创建的对象，关闭时可以直接引用）
3. 是 FastAPI 官方推荐的方式
