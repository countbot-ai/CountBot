# Uvicorn 启动参数说明

## 1、什么是 Uvicorn

Uvicorn 是一个高性能的 ASGI 服务器，用于运行 FastAPI、Starlette 等异步 Python Web 框架。它的角色类似于 Java 生态中的 Tomcat、Node.js 生态中 Express 自带的 HTTP 服务器。

### （1）跨生态对比

| Java 生态 | Python 生态 | Node.js 生态 |
|-----------|------------|-------------|
| Tomcat（服务器） | Uvicorn（服务器） | Node HTTP Server（服务器） |
| Spring Boot（框架） | FastAPI（框架） | Express（框架） |
| Servlet 规范（接口标准） | ASGI 规范（接口标准） | — |

区别：Tomcat 比较"重"，自身功能很多（线程池管理、JSP 编译、Session 管理等），而 Uvicorn 非常轻量，只专注做一件事——高效地处理 HTTP 连接并转发给 ASGI 应用。

## 2、基本用法

```python
import uvicorn

uvicorn.run(
    "backend.app:app",
    host="127.0.0.1",
    port=8000,
    reload=False,
    log_level="info"
)
```

## 3、参数详解

### （1）app（第一个参数）

```python
"backend.app:app"
```

- 格式：`"模块路径:对象名"`
- `backend.app` → 对应文件 `backend/app.py`
- `:app` → 该文件中的 FastAPI 实例变量名
- 用字符串而非直接传对象，是因为 uvicorn 需要自己控制模块的导入过程（特别是 reload 模式下需要重新导入）

也可以直接传对象（但不支持 reload）：

```python
from backend.app import app
uvicorn.run(app, host="127.0.0.1", port=8000)
```

### （2）host

监听的网络地址：

| 值 | 含义 |
|---|------|
| `127.0.0.1` | 只允许本机访问（默认，安全） |
| `0.0.0.0` | 允许所有网络接口访问（局域网、外网） |
| `::` | 同 `0.0.0.0`，但是 IPv6 写法 |
| `192.168.1.100` | 只监听特定网卡的 IP |

### （3）port

监听的端口号，默认 `8000`。启动后通过 `http://host:port` 访问。

常见端口约定：
- `8000` - Python Web 开发常用
- `3000` - Node.js/React 开发常用
- `80` - HTTP 默认端口（需要 root 权限）
- `443` - HTTPS 默认端口

### （4）reload

是否开启热重载：

| 值 | 含义 | 适用场景 |
|---|------|---------|
| `True` | 文件修改后自动重启服务器 | 开发环境 |
| `False` | 不自动重启 | 生产环境 |

注意：`reload=True` 时，app 参数**必须用字符串**形式传入。

### （5）log_level

日志级别，从低到高：

| 级别 | 说明 |
|------|------|
| `debug` | 最详细，包含所有调试信息 |
| `info` | 一般信息（推荐） |
| `warning` | 警告信息 |
| `error` | 错误信息 |
| `critical` | 严重错误 |

级别越高，输出的日志越少。设为 `info` 表示只显示 info 及以上级别的日志。

## 4、其他常用参数

```python
uvicorn.run(
    "backend.app:app",
    host="0.0.0.0",
    port=8000,
    reload=True,              # 热重载
    reload_dirs=["backend"],  # 只监听 backend 目录的文件变化
    workers=4,                # 启动 4 个工作进程（生产环境提升并发）
    log_level="info",
    access_log=True,          # 记录每个请求的访问日志
    ssl_keyfile="key.pem",    # HTTPS 私钥
    ssl_certfile="cert.pem",  # HTTPS 证书
)
```

## 5、命令行启动（等价写法）

除了在代码中调用 `uvicorn.run()`，也可以直接用命令行启动：

```bash
uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload --log-level info
```
