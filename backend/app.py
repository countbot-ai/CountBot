"""FastAPI 应用入口"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from backend.utils.logger import setup_logger

setup_logger()


def _create_shared_components(config):
    """创建共享组件（WebSocket 和渠道处理器共用）"""
    from loguru import logger
    from backend.modules.providers.litellm_provider import LiteLLMProvider
    from backend.modules.providers.registry import get_provider_metadata
    from backend.modules.agent.context import ContextBuilder
    from backend.modules.agent.memory import MemoryStore
    from backend.modules.agent.skills import SkillsLoader
    from backend.modules.agent.subagent import SubagentManager
    from backend.modules.tools.setup import register_all_tools
    from backend.utils.paths import WORKSPACE_DIR

    logger.info("Getting provider metadata...")
    provider_id = config.model.provider
    provider_config = config.providers.get(provider_id)
    provider_meta = get_provider_metadata(provider_id)

    api_key = provider_config.api_key if provider_config else None
    api_base = (
        provider_config.api_base
        if provider_config and provider_config.api_base
        else (provider_meta.default_api_base if provider_meta else None)
    )

    logger.info("Setting up workspace...")
    # 使用统一的工作区路径，如果配置中指定了路径则使用配置的
    if config.workspace.path:
        workspace = Path(config.workspace.path)
    else:
        workspace = WORKSPACE_DIR  # 使用统一路径管理的默认工作区
    workspace.mkdir(parents=True, exist_ok=True)

    logger.info("Creating LiteLLM provider...")
    provider = LiteLLMProvider(
        api_key=api_key,
        api_base=api_base,
        default_model=config.model.model,
        timeout=120.0,
        max_retries=3,
        provider_id=provider_id,
    )

    logger.info("Creating memory and skills directories...")
    memory_dir = workspace / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    skills_dir = workspace / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Initializing memory store...")
    memory = MemoryStore(memory_dir)
    
    logger.info("Loading skills...")
    skills = SkillsLoader(skills_dir)

    logger.info("Building context builder...")
    context_builder = ContextBuilder(
        workspace=workspace,
        memory=memory,
        skills=skills,
        persona_config=config.persona,
    )

    logger.info("Creating subagent manager...")
    subagent_manager = SubagentManager(
        provider=provider,
        workspace=workspace,
        model=config.model.model,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens,
    )

    logger.info("Preparing tool parameters...")
    tool_params = dict(
        workspace=workspace,
        command_timeout=config.security.command_timeout,
        max_output_length=config.security.max_output_length,
        allow_dangerous=not config.security.dangerous_commands_blocked,
        restrict_to_workspace=config.security.restrict_to_workspace,
        custom_deny_patterns=config.security.custom_deny_patterns,
        custom_allow_patterns=(
            config.security.custom_allow_patterns
            if config.security.command_whitelist_enabled
            else None
        ),
        audit_log_enabled=config.security.audit_log_enabled,
        subagent_manager=subagent_manager,
        skills_loader=skills,
    )

    logger.info("Registering all tools...")
    tool_registry = register_all_tools(**tool_params, memory_store=memory)
    logger.info(f"Registered {len(tool_registry)} tools")

    return dict(
        provider=provider,
        workspace=workspace,
        context_builder=context_builder,
        subagent_manager=subagent_manager,
        tool_registry=tool_registry,
        tool_params=tool_params,
        memory=memory,
        skills=skills,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    from backend.database import init_db, get_db_session_factory
    from backend.modules.config.loader import config_loader
    from backend.modules.channels.manager import ChannelManager
    from backend.modules.messaging.enterprise_queue import EnterpriseMessageQueue
    from backend.modules.messaging.rate_limiter import RateLimiter
    from backend.modules.channels.handler import ChannelMessageHandler
    from backend.modules.cron.executor import CronExecutor
    from backend.modules.cron.scheduler import CronScheduler
    from backend.modules.cron.service import CronService
    from backend.modules.agent.loop import AgentLoop
    from backend.modules.session.manager import SessionManager
    from backend.modules.tools.setup import register_all_tools
    from backend.api.channels import set_channel_manager

    # 初始化数据库和配置
    logger.info("Starting CountBot backend...")
    await init_db()
    logger.info("Database initialized")
    await config_loader.load()
    logger.info("Configuration loaded")
    config = config_loader.config

    # 创建共享组件
    logger.info("Creating shared components...")
    shared = _create_shared_components(config)
    app.state.shared = shared
    logger.info("Shared components created")

    logger.info("Creating message queue and rate limiter...")
    message_queue = EnterpriseMessageQueue(
        enable_dedup=True, 
        dedup_window=10
    )
    rate_limiter = RateLimiter(rate=10, per=60)
    logger.info("Message queue and rate limiter created")

    # 创建渠道消息处理器
    logger.info("Creating message handler...")
    message_handler = ChannelMessageHandler(
        provider=shared["provider"],
        workspace=shared["workspace"],
        model=config.model.model,
        bus=message_queue,
        context_builder=shared["context_builder"],
        tool_params=shared["tool_params"],
        subagent_manager=shared["subagent_manager"],
        max_iterations=config.model.max_iterations,
        rate_limiter=rate_limiter,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens,
        max_history_messages=config.persona.max_history_messages,
        memory_store=shared["memory"],
    )
    app.state.message_handler = message_handler
    logger.info("Message handler created")

    # 创建渠道管理器
    logger.info("Creating channel manager...")
    channel_manager = ChannelManager(config, message_queue)
    set_channel_manager(channel_manager)
    message_handler.set_channel_manager(channel_manager)
    logger.info("Channel manager created")

    # 初始化 OSS 上传器（可选）
    logger.info("Initializing OSS uploader (optional)...")
    try:
        from backend.modules.tools.image_uploader import init_oss_uploader
        oss_config = None
        if hasattr(config.channels, "qq") and hasattr(config.channels.qq, "oss"):
            oss_config = config.channels.qq.oss.model_dump()
        init_oss_uploader(oss_config)
        logger.info("OSS uploader initialized")
    except Exception as e:
        logger.warning(f"OSS uploader init failed (optional): {e}")

    # 启动后台任务（不等待完成）
    app.state.background_tasks = []
    if channel_manager.enabled_channels:
        task = asyncio.create_task(channel_manager.start_all())
        app.state.background_tasks.append(task)
        logger.info(f"Started {len(channel_manager.enabled_channels)} channel(s) in background")
    
    task = asyncio.create_task(message_handler.start_processing())
    app.state.background_tasks.append(task)
    logger.info("Started message handler in background")

    # 初始化定时任务系统
    logger.info("Initializing cron system...")
    cron_tool_registry = register_all_tools(
        **shared["tool_params"],
    )
    cron_agent = AgentLoop(
        provider=shared["provider"],
        workspace=shared["workspace"],
        tools=cron_tool_registry,
        context_builder=shared["context_builder"],
        subagent_manager=shared["subagent_manager"],
        model=config.model.model,
        max_iterations=config.model.max_iterations,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens,
    )
    session_manager = SessionManager(shared["workspace"])
    logger.info("Cron agent and session manager created")

    # 初始化心跳服务
    logger.info("Initializing heartbeat service...")
    db_session_factory = get_db_session_factory()

    from backend.modules.agent.heartbeat import HeartbeatService, ensure_heartbeat_job
    heartbeat_config = config.persona.heartbeat
    heartbeat_service = HeartbeatService(
        provider=shared["provider"],
        model=config.model.model,
        workspace=shared["workspace"],
        db_session_factory=db_session_factory,
        ai_name=config.persona.ai_name or "小C",
        user_name=config.persona.user_name or "主人",
        user_address=config.persona.user_address or "",
        personality=config.persona.personality or "professional",
        custom_personality=config.persona.custom_personality or "",
        idle_threshold_hours=heartbeat_config.idle_threshold_hours,
        quiet_start=heartbeat_config.quiet_start,
        quiet_end=heartbeat_config.quiet_end,
        max_greets_per_day=heartbeat_config.max_greets_per_day,
    )
    logger.info("Heartbeat service created")

    logger.info("Creating cron executor...")
    cron_executor = CronExecutor(
        agent=cron_agent,
        bus=message_queue,
        session_manager=session_manager,
        channel_manager=channel_manager,
        heartbeat_service=heartbeat_service,
    )
    logger.info("Cron executor created")

    async def on_cron_execute(
        job_id: str, message: str, channel: str, chat_id: str, deliver_response: bool
    ) -> str:
        return await cron_executor.execute(
            job_id, message, channel, chat_id, deliver_response
        )

    logger.info("Creating cron scheduler...")
    scheduler = CronScheduler(
        db_session_factory=db_session_factory,
        on_execute=on_cron_execute,
    )
    await scheduler.start()
    logger.info("Cron scheduler started")

    # 注册内置心跳任务
    logger.info("Ensuring heartbeat job...")
    await ensure_heartbeat_job(db_session_factory, heartbeat_config=heartbeat_config)
    await scheduler.trigger_reschedule()
    logger.info("Heartbeat job ensured")

    app.state.cron_scheduler = scheduler
    app.state.cron_executor = cron_executor

    async def get_cron_service_for_tool():
        async with db_session_factory() as db:
            return CronService(db, scheduler=scheduler)

    app.state.get_cron_service = get_cron_service_for_tool

    # 注册进程退出清理处理器（备用机制）
    import atexit
    
    def cleanup_on_exit() -> None:
        """进程退出时的清理函数"""
        logger.info("atexit cleanup triggered")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(channel_manager.stop_all())
            finally:
                loop.close()
        except RuntimeError as e:
            logger.debug(f"Event loop already closed: {e}")
        except Exception as e:
            logger.error(f"Error in atexit cleanup: {e}")
    
    atexit.register(cleanup_on_exit)

    logger.info("Backend started successfully")

    yield

    # 正常关闭流程
    logger.info("Initiating graceful shutdown...")
    await channel_manager.stop_all()
    await scheduler.stop()
    logger.info("Backend shutdown complete")


app = FastAPI(
    title="CountBot Desktop API",
    description="CountBot backend API",
    version="0.1.0",
    lifespan=lifespan,
)

# 保存绑定地址用于认证判断
import os as _os
app.state.bind_host = _os.getenv("HOST", "127.0.0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 远程访问认证中间件
from backend.modules.auth.middleware import RemoteAuthMiddleware
from backend.modules.auth.router import get_password_hash

app.add_middleware(RemoteAuthMiddleware, get_password_hash_fn=get_password_hash)

# 注册 API 路由
from backend.api.chat import router as chat_router
from backend.api.settings import router as settings_router
from backend.api.tools import router as tools_router
from backend.api.memory import router as memory_router
from backend.api.skills import router as skills_router
from backend.api.cron import router as cron_router
from backend.api.tasks import router as tasks_router
from backend.api.audio import router as audio_router
from backend.api.system import router as system_router
from backend.api.channels import router as channels_router
from backend.api.queue import router as queue_router
from backend.api.auth import router as auth_router
from backend.api.personalities import router as personalities_router

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(settings_router)
app.include_router(tools_router)
app.include_router(memory_router)
app.include_router(skills_router)
app.include_router(cron_router)
app.include_router(tasks_router)
app.include_router(audio_router)
app.include_router(system_router)
app.include_router(channels_router)
app.include_router(queue_router)
app.include_router(personalities_router)


# WebSocket 端点
from fastapi import WebSocket
from backend.ws.connection import handle_websocket


@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 聊天端点，复用共享组件"""
    from backend.modules.agent.loop import AgentLoop
    from backend.modules.providers.litellm_provider import LiteLLMProvider
    from backend.modules.providers.registry import get_provider_metadata
    from backend.modules.tools.setup import register_all_tools

    # 远程访问认证检查
    from backend.modules.auth.middleware import LOCAL_IPS
    from backend.modules.auth.utils import validate_session as validate_ws_session
    from backend.modules.auth.router import get_password_hash as get_ws_password_hash

    # TCP 层面获取真实客户端 IP
    client_ip = websocket.client.host if websocket.client else None
    
    if not client_ip:
        logger.warning("WebSocket connection rejected: unable to determine client IP")
        await websocket.close(code=1008, reason="Unable to determine client IP")
        return
    
    # 检测代理头（
    proxy_headers = {
        "x-forwarded-for", "x-real-ip", "x-forwarded-host", 
        "x-forwarded-proto", "forwarded", "via", "x-forwarded-server",
        "x-cluster-client-ip", "cf-connecting-ip", "true-client-ip"
    }
    request_headers = {k.lower() for k in websocket.headers.keys()}
    has_proxy = bool(proxy_headers & request_headers)
    
    # TCP 层面判断是否为本地连接（无法通过 HTTP 头伪造）
    is_local = client_ip in LOCAL_IPS and not has_proxy
    
    if has_proxy:
        logger.info(f"WebSocket proxy headers detected, treating as remote (socket IP: {client_ip})")
    
    logger.info(f"WebSocket connection from {client_ip} ({'local' if is_local else 'remote'})")

    if not is_local:
        pw_hash = ""
        try:
            pw_hash = await get_ws_password_hash()
        except Exception:
            pass

        if pw_hash:
            token = websocket.query_params.get("token") or websocket.cookies.get("CountBot_token")
            if not token or not validate_ws_session(token):
                await websocket.close(code=4001, reason="Authentication required")
                return

    shared = websocket.app.state.shared

    # 每个 WebSocket 连接使用独立的工具注册表（会话隔离）
    tool_registry = register_all_tools(
        **shared["tool_params"],
        memory_store=shared["memory"],
    )

    from backend.modules.config.loader import config_loader
    config = config_loader.config

    # 根据当前配置创建 provider（支持动态切换）
    provider_id = config.model.provider
    provider_config = config.providers.get(provider_id)
    provider_meta = get_provider_metadata(provider_id)

    api_key = provider_config.api_key if provider_config else None
    api_base = (
        provider_config.api_base
        if provider_config and provider_config.api_base
        else (provider_meta.default_api_base if provider_meta else None)
    )

    provider = LiteLLMProvider(
        api_key=api_key,
        api_base=api_base,
        default_model=config.model.model,
        timeout=120.0,
        max_retries=3,
        provider_id=provider_id,
    )

    agent_loop = AgentLoop(
        provider=provider,
        workspace=shared["workspace"],
        tools=tool_registry,
        context_builder=shared["context_builder"],
        subagent_manager=shared["subagent_manager"],
        model=config.model.model,
        max_iterations=config.model.max_iterations,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens,
    )

    await handle_websocket(websocket, agent_loop=agent_loop)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}


# 挂载前端静态文件
from backend.utils.paths import APPLICATION_ROOT

frontend_dist = APPLICATION_ROOT / "frontend" / "dist"
if frontend_dist.exists():
    from fastapi.responses import FileResponse
    import mimetypes
    
    # 确保 Windows 上正确识别 JavaScript 模块的 MIME 类型
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("image/svg+xml", ".svg")

    # SPA 路由回退（必须在 StaticFiles 之前注册）
    @app.get("/login")
    async def spa_login():
        return FileResponse(str(frontend_dist / "index.html"))

    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")
