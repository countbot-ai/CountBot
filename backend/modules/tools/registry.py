"""Tool Registry - 工具注册表"""

import contextvars
import uuid
from typing import Any
from datetime import datetime

from loguru import logger

from backend.modules.tools.base import Tool
from backend.modules.tools.file_audit_logger import file_audit_logger

# 使用 contextvars 实现异步安全的 session_id 存储
# 每个异步任务都有独立的上下文，避免并发冲突
_session_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'session_id', default=None
)
_channel_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'channel', default=None
)

# 代理上下文
_agent_type_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    'agent_type', default='main'
)
_agent_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'agent_id', default=None
)
_workflow_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'workflow_id', default=None
)
_parent_tool_call_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    'parent_tool_call_id', default=None
)


class ToolRegistry:
    """工具注册表 - 管理所有可用工具的注册、查询和执行"""

    def __init__(self):
        """初始化工具注册表"""
        self._tools: dict[str, Tool] = {}
        self._audit_enabled: bool = True
        # 注意：不再使用实例变量存储 session_id，改用 contextvars
        logger.debug("ToolRegistry initialized (using contextvars for session isolation)")
    
    def set_audit_enabled(self, enabled: bool) -> None:
        """设置是否启用审计日志"""
        self._audit_enabled = enabled
        file_audit_logger.set_enabled(enabled)
        logger.debug(f"Audit logging {'enabled' if enabled else 'disabled'}")
    
    def set_session_id(self, session_id: str | None) -> None:
        """设置当前上下文的会话 ID（异步安全）
        
        使用 contextvars 确保每个异步任务都有独立的 session_id，
        避免并发请求之间的相互覆盖。
        """
        _session_id_context.set(session_id)

        # 遍历所有工具，更新支持 set_session_id 的工具
        for tool in self._tools.values():
            if hasattr(tool, 'set_session_id'):
                tool.set_session_id(session_id)
    
    @property
    def _session_id(self) -> str | None:
        """获取当前上下文的会话 ID（异步安全）"""
        return _session_id_context.get()

    def set_cancel_token(self, token) -> None:
        """设置取消令牌，并传递给所有支持 set_cancel_token 的工具（如 WorkflowTool）。"""
        for tool in self._tools.values():
            if hasattr(tool, 'set_cancel_token'):
                tool.set_cancel_token(token)

    def set_agent_context(
        self,
        agent_type: str = "main",
        agent_id: str | None = None,
        workflow_id: str | None = None,
        parent_tool_call_id: str | None = None,
    ) -> None:
        """设置代理上下文信息（异步安全）
        
        Args:
            agent_type: 代理类型（main / subagent / workflow）
            agent_id: 子代理 ID
            workflow_id: 工作流 ID
            parent_tool_call_id: 父工具调用 ID
        """
        _agent_type_context.set(agent_type)
        _agent_id_context.set(agent_id)
        _workflow_id_context.set(workflow_id)
        _parent_tool_call_id_context.set(parent_tool_call_id)
    
    def set_channel(self, channel: str | None) -> None:
        """设置当前上下文的消息来源渠道（异步安全）
        
        如 dingtalk, telegram, web-chat
        """
        _channel_context.set(channel)

        # 更新记忆工具的默认来源（兼容统一 memory 工具和旧版 memory_write 工具）
        memory_tool = self._tools.get('memory') or self._tools.get('memory_write')
        if memory_tool and hasattr(memory_tool, 'set_channel'):
            memory_tool.set_channel(channel)

    @property
    def channel(self) -> str | None:
        """获取当前上下文的渠道（异步安全）"""
        return _channel_context.get()

    def register(self, tool: Tool) -> None:
        """
        注册工具
        
        Args:
            tool: 要注册的工具实例
            
        Raises:
            ValueError: 如果工具名称已存在
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def unregister(self, tool_name: str) -> bool:
        """
        注销工具
        
        Args:
            tool_name: 工具名称
            
        Returns:
            bool: 是否成功注销
        """
        if tool_name in self._tools:
            del self._tools[tool_name]
            logger.debug(f"Unregistered tool: {tool_name}")
            return True
        else:
            logger.warning(f"Tool '{tool_name}' not found for unregistration")
            return False

    def get_tool(self, tool_name: str) -> Tool | None:
        """
        获取工具实例
        
        Args:
            tool_name: 工具名称
            
        Returns:
            Tool | None: 工具实例，如果不存在则返回 None
        """
        return self._tools.get(tool_name)

    def has_tool(self, tool_name: str) -> bool:
        """
        检查工具是否已注册
        
        Args:
            tool_name: 工具名称
            
        Returns:
            bool: 工具是否存在
        """
        return tool_name in self._tools

    def list_tools(self) -> list[str]:
        """
        列出所有已注册的工具名称
        
        Returns:
            list[str]: 工具名称列表
        """
        return list(self._tools.keys())

    def get_definitions(self) -> list[dict[str, Any]]:
        """
        获取所有工具的定义
        
        用于生成 LLM 函数调用的工具列表。
        
        Returns:
            list[dict]: 工具定义列表
        """
        definitions = [tool.get_definition() for tool in self._tools.values()]
        logger.debug(f"Generated {len(definitions)} tool definitions")
        return definitions

    async def execute(self, tool_name: str, arguments: dict[str, Any], auto_record: bool = True) -> str:
        """
        执行工具
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            auto_record: 是否自动记录到工具对话历史（默认 True）
            
        Returns:
            str: 工具执行结果（包括错误信息）
            
        Note:
            此方法不会抛出异常，而是返回错误字符串
        """
        tool = self.get_tool(tool_name)
        
        if tool is None:
            error_msg = f"Tool '{tool_name}' not found. Please use only the tools provided in the tool definitions."
            logger.warning(f"Tool not found: {tool_name} (this may be an LLM hallucination)")
            return error_msg
        
        # 生成调用 ID
        call_id = str(uuid.uuid4())
        start_time = datetime.now()
        
        # 记录工具调用到文件（如果启用审计日志）
        if self._audit_enabled:
            file_audit_logger.record_call(
                call_id=call_id,
                tool_name=tool_name,
                arguments=arguments,
                session_id=self._session_id
            )
        
        try:
            # 验证参数
            errors = tool.validate_params(arguments)
            if errors:
                error_msg = f"Error: Invalid parameters for tool '{tool_name}': " + "; ".join(errors)
                logger.error(error_msg)
                
                # 记录到工具对话历史（参数验证失败）
                if auto_record and self._session_id:
                    try:
                        from backend.modules.tools.conversation_history import get_conversation_history
                        conversation_history = get_conversation_history()
                        conversation_history.add_conversation(
                            session_id=self._session_id,
                            tool_name=tool_name,
                            arguments=arguments,
                            error=error_msg,
                            duration_ms=0
                        )
                    except Exception as conv_err:
                        logger.warning(f"Failed to record tool conversation: {conv_err}")
                
                return error_msg
            
            logger.info(f"Executing tool: {tool_name} with arguments: {arguments}")
            result = await tool.execute(**arguments)
            
            # 计算执行时间
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            # 更新审计日志
            if self._audit_enabled:
                file_audit_logger.update_result(call_id, result, "success", duration_ms=duration_ms)
            
            # 记录到工具对话历史（成功）
            if auto_record and self._session_id:
                try:
                    from backend.modules.tools.conversation_history import get_conversation_history
                    conversation_history = get_conversation_history()
                    conversation_history.add_conversation(
                        session_id=self._session_id,
                        tool_name=tool_name,
                        arguments=arguments,
                        result=result,
                        duration_ms=duration_ms,
                    )
                except Exception as conv_err:
                    logger.warning(f"Failed to record tool conversation: {conv_err}")
            
            logger.info(f"Tool '{tool_name}' executed successfully")
            return result
            
        except Exception as e:
            error_msg = f"Error executing {tool_name}: {str(e)}"
            logger.error(error_msg)
            
            # 计算执行时间
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            # 更新审计日志
            if self._audit_enabled:
                file_audit_logger.update_result(call_id, str(e), "error", error=str(e), duration_ms=duration_ms)
            
            # 记录到工具对话历史（失败）
            if auto_record and self._session_id:
                try:
                    from backend.modules.tools.conversation_history import get_conversation_history
                    conversation_history = get_conversation_history()
                    conversation_history.add_conversation(
                        session_id=self._session_id,
                        tool_name=tool_name,
                        arguments=arguments,
                        error=error_msg,
                        duration_ms=duration_ms,
                    )
                except Exception as conv_err:
                    logger.warning(f"Failed to record tool conversation: {conv_err}")
            
            return error_msg

    def get_stats(self) -> dict[str, Any]:
        """
        获取注册表统计信息
        
        Returns:
            dict: 统计信息
        """
        stats = {
            "total_tools": len(self._tools),
            "tool_names": self.list_tools(),
        }
        logger.debug(f"Registry stats: {stats}")
        return stats

    def clear(self) -> None:
        """清空所有已注册的工具"""
        count = len(self._tools)
        self._tools.clear()
        logger.info(f"Cleared {count} tools from registry")

    @property
    def tool_names(self) -> list[str]:
        """
        获取所有已注册的工具名称列表
        
        Returns:
            list[str]: 工具名称列表
        """
        return list(self._tools.keys())

    def __len__(self) -> int:
        """返回已注册工具的数量"""
        return len(self._tools)

    def __contains__(self, tool_name: str) -> bool:
        """检查工具是否已注册（支持 'name' in registry 语法）"""
        return tool_name in self._tools
