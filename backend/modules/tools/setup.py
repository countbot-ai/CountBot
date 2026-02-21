"""工具注册统一配置模块"""

from pathlib import Path
from loguru import logger

from backend.modules.tools.registry import ToolRegistry


def register_all_tools(
    workspace: Path,
    command_timeout: int = 30,
    max_output_length: int = 10000,
    allow_dangerous: bool = False,
    restrict_to_workspace: bool = True,
    custom_deny_patterns: list[str] | None = None,
    custom_allow_patterns: list[str] | None = None,
    audit_log_enabled: bool = True,
    subagent_manager=None,
    skills_loader=None,
    session_id: str | None = None,
    channel_manager=None,
    session_manager=None,
    memory_store=None,
) -> ToolRegistry:
    """
    注册所有可用工具
    
    Args:
        workspace: 工作空间路径
        command_timeout: 命令超时时间（秒）
        max_output_length: 最大输出长度（字符）
        allow_dangerous: 是否允许危险命令
        restrict_to_workspace: 是否限制在工作空间内
        custom_deny_patterns: 自定义拒绝模式列表
        custom_allow_patterns: 自定义允许模式列表
        audit_log_enabled: 是否启用审计日志
        subagent_manager: SubagentManager 实例（可选）
        skills_loader: SkillsLoader 实例（可选，用于检查禁用的技能）
        session_id: 会话 ID（可选，用于审计日志）
        channel_manager: ChannelManager 实例（可选）
        session_manager: SessionManager 实例（可选）
        memory_store: MemoryStore 实例（可选，用于记忆工具）
        
    Returns:
        ToolRegistry: 已注册所有工具的注册表
    """
    tools = ToolRegistry()
    
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
        from backend.modules.tools.shell import DANGEROUS_PATTERNS
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
            
            spawn_tool = SpawnTool(subagent_manager)
            tools.register(spawn_tool)
            logger.debug("Registered spawn tool")
        except Exception as e:
            logger.error(f"Failed to register spawn tool: {e}")
    
    # 5. 注册发送媒体工具（如果提供了 ChannelManager）
    if channel_manager is not None:
        try:
            from backend.modules.tools.send_media import SendMediaTool
            
            send_media_tool = SendMediaTool(
                channel_manager=channel_manager,
                session_manager=session_manager
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
        
        file_search_tool = FileSearchTool(default_max_results=20)
        tools.register(file_search_tool)
        logger.debug("Registered file search tool")
    except Exception as e:
        logger.error(f"Failed to register file search tool: {e}")
    
    # 8. 注册记忆工具
    if memory_store is not None:
        try:
            from backend.modules.tools.memory_tool import (
                MemoryWriteTool,
                MemorySearchTool,
                MemoryReadTool,
            )
            
            tools.register(MemoryWriteTool(memory_store))
            tools.register(MemorySearchTool(memory_store))
            tools.register(MemoryReadTool(memory_store))
            logger.debug("Registered memory tools")
        except Exception as e:
            logger.error(f"Failed to register memory tools: {e}")
    
    logger.debug(f"Registered {len(tools.get_definitions())} tools")
    return tools
