"""工具注册统一配置模块"""

from typing import Iterable, List, Optional
from pathlib import Path
from loguru import logger

from backend.modules.tools.registry import ToolRegistry


def register_all_tools(
    workspace: Path,
    command_timeout: int = 180,
    max_output_length: int = 10000,
    allow_dangerous: bool = False,
    restrict_to_workspace: bool = True,
    custom_deny_patterns: Optional[List[str]] = None,
    custom_allow_patterns: Optional[List[str]] = None,
    audit_log_enabled: bool = True,
    subagent_manager=None,
    skills_loader=None,
    session_id: Optional[str] = None,
    owner_id: Optional[str] = None,
    channel_manager=None,
    session_manager=None,
    memory_store=None,
    config_loader=None,
    disabled_tools: Optional[Iterable[str]] = None,
    current_user=None,
) -> ToolRegistry:
    """注册所有可用工具并返回工具注册表。"""
    # 保存构建参数，供 sync_disabled_tools 重建注册表
    build_params = dict(locals())

    tools = ToolRegistry(workspace=workspace)
    
    # 配置审计日志
    tools.set_audit_enabled(audit_log_enabled)
    if session_id:
        tools.set_session_id(session_id)
    
    # 1. 注册文件系统工具（AI 可用，但前端隐藏）
    from backend.modules.tools.filesystem import (
        ReadFileTool,
        WriteFileTool,
        EditFileTool,
        ListDirTool,
    )
    
    tools.register(ReadFileTool(workspace, skills_loader=skills_loader, restrict_to_workspace=restrict_to_workspace))
    tools.register(WriteFileTool(workspace, restrict_to_workspace=restrict_to_workspace))
    tools.register(EditFileTool(workspace, restrict_to_workspace=restrict_to_workspace))
    tools.register(ListDirTool(workspace, restrict_to_workspace=restrict_to_workspace))
    logger.debug("Registered filesystem tools")
    
    # 2. 注册 Shell 工具（AI 可用，但前端隐藏）
    from backend.modules.tools.shell import ExecTool
    
    # 合并自定义拒绝模式
    deny_patterns = None
    if custom_deny_patterns:
        from backend.modules.tools.command_guard import DANGEROUS_PATTERNS
        deny_patterns = list(DANGEROUS_PATTERNS) + custom_deny_patterns
    
    tools.register(
        ExecTool(
            workspace=workspace,
            timeout=command_timeout,
            max_output_length=max_output_length,
            allow_dangerous=allow_dangerous,
            deny_patterns=deny_patterns,
            allow_patterns=custom_allow_patterns,
            restrict_to_workspace=restrict_to_workspace,
        )
    )
    logger.debug(
        f"Registered shell tools (dangerous_blocked={not allow_dangerous}, "
        f"workspace_restricted={restrict_to_workspace})"
    )

    # 2b. 注册外部编程代理工具
    try:
        from backend.modules.tools.external_coding_agent import ExternalCodingAgentTool

        external_coding_tool = ExternalCodingAgentTool(
            workspace=workspace,
            default_timeout=command_timeout,
            max_output_length=max_output_length,
        )
        enabled_profiles = external_coding_tool.registry.enabled_profile_names()
        if enabled_profiles:
            if session_id:
                external_coding_tool.set_session_id(session_id)
            tools.register(external_coding_tool)
            logger.debug(
                "Registered external coding agent tool with enabled profiles: {}",
                ", ".join(enabled_profiles),
            )
        else:
            logger.info("Skipped external coding agent tool registration: no enabled profiles")
    except Exception as e:
        logger.error(f"Failed to register external coding agent tool: {e}")
    
    # 3. 注册 Web 工具
    try:
        from backend.modules.tools.web import WebFetchTool
        
        tools.register(WebFetchTool())
        logger.debug("Registered web fetch tool")
    except ImportError:
        logger.warning("Web tools not available")
    
    # 4. 注册 Spawn 工具（如果提供了 SubagentManager）
    if subagent_manager is not None:
        try:
            from backend.modules.tools.spawn import SpawnTool

            spawn_tool = SpawnTool(subagent_manager, config_loader=config_loader)
            tools.register(spawn_tool)
            logger.debug("Registered spawn tool")
        except Exception as e:
            logger.error(f"Failed to register spawn tool: {e}")

    # 4b. 注册 Workflow 工具（如果提供了 SubagentManager）
    if subagent_manager is not None:
        try:
            from backend.modules.tools.workflow_tool import WorkflowTool

            workflow_tool = WorkflowTool(
                subagent_manager, skills=skills_loader, owner_id=owner_id
            )
            if session_id:
                workflow_tool.set_session_id(session_id)
            tools.register(workflow_tool)
            logger.debug("Registered workflow_run tool")
        except Exception as e:
            logger.error(f"Failed to register workflow_run tool: {e}")
    
    # 4c. 注册 Dynamic Workflow 工具（独立 JSON AST 运行时）
    if subagent_manager is not None:
        try:
            from backend.database import get_db_session_factory
            from backend.modules.workflow.factory import DynamicActorFactory
            from backend.modules.workflow.journal import WorkflowJournal
            from backend.modules.workflow.service import DynamicWorkflowService
            from backend.modules.tools.dynamic_workflow_tool import DynamicWorkflowTool

            dwf_journal = WorkflowJournal(get_db_session_factory())
            dwf_factory = DynamicActorFactory(
                subagent_manager=subagent_manager,
                workspace=workspace,
                owner_id=owner_id,
                session_id=session_id,
            )

            async def dwf_driver_factory(**kwargs):
                return await dwf_factory.build_dynamic_driver(
                    run_id=kwargs["run_id"],
                    program=kwargs["program"],
                    journal=dwf_journal,
                    lineage=kwargs.get("lineage", ()),
                    user=kwargs.get("user"),
                    runtime=kwargs.get("runtime"),
                )

            dwf_service = DynamicWorkflowService(dwf_driver_factory, dwf_journal)
            tools.register(DynamicWorkflowTool(
                dwf_service,
                owner_id=owner_id,
                session_id=session_id,
                workspace=workspace,
                user=current_user,
            ))
            logger.debug("Registered dynamic_workflow_run tool")
        except Exception as e:
            logger.error(f"Failed to register dynamic_workflow_run tool: {e}")

    # 5. 注册发送媒体工具（如果提供了 ChannelManager）
    if channel_manager is not None:
        try:
            from backend.modules.tools.send_media import SendMediaTool
            
            send_media_tool = SendMediaTool(
                channel_manager=channel_manager,
                session_manager=session_manager,
                workspace=workspace,
            )
            # 设置当前会话 ID
            if session_id:
                send_media_tool.set_session_id(session_id)
            tools.register(send_media_tool)
            logger.debug("Registered send_media tool")
        except Exception as e:
            logger.error(f"Failed to register send_media tool: {e}")
    
    # 6. 注册截图工具
    try:
        from backend.modules.tools.screenshot import ScreenshotTool
        
        screenshot_tool = ScreenshotTool(workspace=workspace)
        tools.register(screenshot_tool)
        logger.debug("Registered screenshot tool")
    except Exception as e:
        logger.error(f"Failed to register screenshot tool: {e}")
    
    # 7. 注册文件搜索工具
    try:
        from backend.modules.tools.file_search import FileSearchTool
        
        file_search_tool = FileSearchTool(
            workspace=workspace,
            default_max_results=20,
            restrict_to_workspace=restrict_to_workspace,
        )
        tools.register(file_search_tool)
        logger.debug("Registered file search tool")
    except Exception as e:
        logger.error(f"Failed to register file search tool: {e}")
    
    # 8. 注册记忆工具（合并为单一工具，减少 token 消耗）
    if memory_store is not None:
        try:
            from backend.modules.tools.memory_tool import MemoryTool

            tools.register(MemoryTool(memory_store))
            logger.debug("Registered memory tool (unified)")
        except Exception as e:
            logger.error(f"Failed to register memory tool: {e}")

    # 8b. 注册 Wiki 知识库工具
    try:
        from backend.modules.wiki.tool import WikiTool

        # 初始化当前工作空间的 wiki 目录，WikiTool 每次调用按当前 workspace 解析目录
        wiki_dir = workspace / "wiki"
        wiki_dir.mkdir(parents=True, exist_ok=True)
        wiki_tool = WikiTool()
        tools.register(wiki_tool)
        logger.debug("Registered wiki tool (follows current workspace wiki dir)")
    except Exception as e:
        logger.error(f"Failed to register wiki tool: {e}")

    # 9. 注册小智AI send_message 工具（仅在小智频道启用且对话模式开启时注册）
    try:
        from backend.modules.config.loader import config_loader as _cl
        xiaozhi_cfg = getattr(getattr(_cl.config, "channels", None), "xiaozhi", None)
        if xiaozhi_cfg and xiaozhi_cfg.enabled and getattr(xiaozhi_cfg, "enable_conversation", False):
            from backend.modules.tools.xiaozhi_message import XiaozhiMessageTool
            tools.register(XiaozhiMessageTool())
            logger.debug("✓ Registered xiaozhi send_message tool (conversation mode enabled)")
        else:
            logger.debug(f"Xiaozhi send_message tool not registered - enabled={xiaozhi_cfg.enabled if xiaozhi_cfg else False}, conversation={getattr(xiaozhi_cfg, 'enable_conversation', False) if xiaozhi_cfg else False}")
    except Exception as e:
        logger.warning(f"Failed to register xiaozhi send_message tool: {e}")

    logger.debug(f"Registered {len(tools.get_definitions())} tools")

    # 10. 应用注入开关：禁用指定工具（injection.disabled_tools）
    if disabled_tools:
        for tool_name in disabled_tools:
            name = str(tool_name or "").strip()
            if not name:
                continue
            if tools.unregister(name):
                logger.info(f"Tool '{name}' disabled by injection config (not exposed to LLM)")
            else:
                logger.warning(
                    f"Injection config requests disabling unknown tool '{name}'; "
                    f"registered tools: {tools.list_tools()}"
                )
        logger.debug(
            f"After injection filtering: {len(tools.get_definitions())} tools"
        )

    tools.build_params = build_params
    return tools


def sync_disabled_tools(registry: ToolRegistry, disabled_tools: Optional[Iterable[str]]) -> bool:
    """按最新注入开关重建工具集，返回是否发生变化。"""
    build_params = getattr(registry, "build_params", None)
    if not isinstance(build_params, dict):
        return False

    target = [str(name).strip() for name in (disabled_tools or []) if str(name).strip()]
    current = [
        str(name).strip()
        for name in (build_params.get("disabled_tools") or [])
        if str(name).strip()
    ]
    if current == target:
        return False

    rebuilt = register_all_tools(**{**build_params, "disabled_tools": target})
    # 就地复用原注册表对象，保持外部引用有效
    registry._tools = rebuilt._tools
    registry._definitions_cache = None
    registry.build_params = rebuilt.build_params
    logger.info(f"Tool registry re-synced with injection config: disabled_tools={target}")
    return True
