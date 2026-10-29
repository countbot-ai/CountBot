"""渠道命令处理器（Mixin）

从 channels/handler.py 拆出的 / 命令处理器（纯搬家，无逻辑改动）。
ChannelMessageHandler 继承本 Mixin；命令处理器通过 self 访问宿主的
会话管理、回复发送、工具注册表等能力，行为与拆分前完全一致。
"""

import json
import time
from typing import Dict, List, Optional

from loguru import logger

from backend.models.message import Message
from backend.models.session import Session
from backend.modules.agent.session_gate import get_session_gate
from backend.modules.agent.task_manager import CancellationToken
from backend.modules.agent.team_commands import (
    build_team_command_overview,
    build_team_goal_usage,
    resolve_explicit_team_command,
)
from backend.modules.channels.base import InboundMessage
from backend.modules.channels.inbound_utils import (
    _WORKFLOW_META_RE,
    _encode_message_context,
    _resolve_session_route,
)
from backend.modules.config.loader import config_loader


class ChannelCommandMixin:
    """渠道 / 命令处理器集合（/new /list /switch /clear /stop /p /m /route /coder /help /team）。"""

    async def _handle_new_session_command(self, msg: InboundMessage) -> None:
        """处理 /new 命令。"""
        import uuid
        from datetime import datetime

        session_route = _resolve_session_route(msg)
        session_name = (
            f"{msg.channel}:{str(session_route['context_owner_account_id'])}:{str(session_route['session_chat_id'])}:"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        session_id = str(uuid.uuid4())

        async with self.db_session_factory() as db:
            channel_context = self._build_session_channel_context(msg, session_route)
            db.add(
                Session(
                    id=session_id,
                    name=session_name,
                    channel_context=(
                        json.dumps(channel_context, ensure_ascii=False)
                        if channel_context
                        else None
                    ),
                )
            )
            await db.commit()

        if not hasattr(self, "_active_sessions"):
            self._active_sessions = {}
        self._active_sessions[self._get_chat_key(msg)] = session_id

        await self._send_reply(
            msg, 
            f"新会话已创建\n\n"
            f"名称: {session_name}\n"
            f"ID: {session_id}\n\n"
            f"现在可以开始新对话了"
        )


    async def _handle_list_sessions_command(
        self, msg: InboundMessage, include_all: bool = False
    ) -> None:
        """处理 /list 和 /al 命令。"""
        sessions = await self._load_recent_sessions(msg, include_all=include_all, limit=10)
        self._remember_session_list_scope(msg, include_all)

        if not sessions:
            empty_text = (
                "暂无会话记录\n\n"
                "使用 /n 创建第一个会话"
                if include_all
                else "当前聊天暂无会话记录\n\n使用 /n 创建第一个会话\n使用 /al 查看所有会话"
            )
            await self._send_reply(msg, empty_text)
            return

        counts = await self._load_session_message_counts([s.id for s in sessions])
        title = "所有会话列表 (最近10个)" if include_all else "当前聊天会话列表 (最近10个)"
        lines = [f"{title}\n━━━━━━━━━━━━━━━━━━━━━━\n"]
        for i, s in enumerate(sessions, 1):
            updated_at = getattr(s, "updated_at", None) or s.created_at
            updated = updated_at.strftime("%Y-%m-%d %H:%M")
            lines.append(
                f"[{i}] {s.name}\n"
                f"    ID: {s.id}\n"
                f"    更新: {updated} | 消息: {counts.get(s.id, 0)}\n"
            )
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("使用 /s <编号|ID> 切换，如: /s 1")
        lines.append("使用 /l 查看当前聊天会话" if include_all else "使用 /al 查看所有会话")
        await self._send_reply(msg, "\n".join(lines))


    async def _handle_switch_session_command(
        self, msg: InboundMessage, content: str
    ) -> None:
        """处理 /switch 命令，支持数字编号或完整ID。"""
        parts = content.split(maxsplit=1)
        if len(parts) < 2:
            await self._send_reply(
                msg, 
                "参数错误\n\n"
                "用法: /s <编号|ID>\n\n"
                "先用 /l 查看当前聊天会话，或 /al 查看所有会话"
            )
            return

        identifier = parts[1].strip()
        last_scope = self._get_last_session_list_scope(msg)
        scope_label = "所有会话" if last_scope == "all" else "当前聊天会话"

        # 尝试作为数字编号解析
        session = None
        if identifier.isdigit():
            sessions = await self._load_recent_sessions(
                msg, include_all=(last_scope == "all"), limit=10
            )
            if not sessions:
                await self._send_reply(
                    msg,
                    "暂无会话记录\n\n"
                    "使用 /l 查看当前聊天会话，或 /al 查看所有会话"
                )
                return

            index = int(identifier) - 1
            if 0 <= index < len(sessions):
                session = sessions[index]
            else:
                await self._send_reply(
                    msg,
                    f"编号 {identifier} 不存在\n\n"
                    f"当前 {scope_label} 中有 {len(sessions)} 个会话\n"
                    f"使用 /l 或 /al 重新查看列表"
                )
                return
        else:
            # 作为完整ID查找
            session = await self._get_session_by_id(identifier)
        
        if not session:
            await self._send_reply(
                msg, 
                f"会话不存在: {identifier}\n\n"
                f"使用 /l 或 /al 查看可用会话"
            )
            return

        if not hasattr(self, "_active_sessions"):
            self._active_sessions = {}
        self._active_sessions[self._get_chat_key(msg)] = session.id
        source_line = f"来源: {scope_label}\n" if identifier.isdigit() else ""
        await self._send_reply(
            msg, 
            f"已切换会话\n\n"
            f"{session.name}\n"
            f"ID: {session.id}\n"
            f"{source_line}\n"
            f"后续消息将继续写入这个会话"
        )


    async def _handle_clear_history_command(self, msg: InboundMessage) -> None:
        """处理 /clear 命令。"""
        from sqlalchemy import delete

        session_id = await self._get_or_create_session(msg)
        async with self.db_session_factory() as db:
            result = await db.execute(
                delete(Message).where(Message.session_id == session_id)
            )
            deleted_count = result.rowcount
            await db.commit()
        
        await self._send_reply(
            msg, 
            f"历史记录已清除\n\n"
            f"已删除 {deleted_count} 条消息"
        )


    async def _handle_stop_command(self, msg: InboundMessage) -> None:
        """处理 /stop 命令。"""
        session_id = await self._get_or_create_session(msg)
        if await self.cancel_task(session_id):
            await self._send_reply(msg, "任务已停止")
        else:
            await self._send_reply(msg, "没有正在执行的任务")


    async def _handle_personality_command(self, msg: InboundMessage, content: str) -> None:
        """处理 /personality 或 /p 命令 - 为当前会话设置性格。"""
        from backend.modules.agent.personalities import PERSONALITY_PRESETS
        from backend.modules.session.runtime_config import resolve_session_runtime_config
        from sqlalchemy import select
        import json
        
        session_id = await self._get_or_create_session(msg)
        parts = content.split(maxsplit=1)
        
        async with self.db_session_factory() as db:
            result = await db.execute(select(Session).where(Session.id == session_id))
            session = result.scalar_one_or_none()
            
            if not session:
                await self._send_reply(msg, "会话不存在")
                return
            
            runtime_config = resolve_session_runtime_config(config_loader.config, session)
            current_personality = runtime_config.persona_config.personality
            
            if len(parts) < 2:
                lines = ["可用性格列表\n━━━━━━━━━━━━━━━━━━━━━━\n"]
                
                personality_list = list(PERSONALITY_PRESETS.items())
                for i, (pid, preset) in enumerate(personality_list, 1):
                    marker = " [当前]" if pid == current_personality else ""
                    lines.append(f"[{i}] {pid} - {preset['name']}{marker}")
                
                lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
                lines.append(f"当前会话性格: {current_personality}")
                lines.append("\n使用 /p <编号|性格ID> 切换")
                lines.append("如: /p 1 或 /p friendly")
                await self._send_reply(msg, "\n".join(lines))
                return
            
            identifier = parts[1].strip().lower()
            personality_id = None
            
            personality_list = list(PERSONALITY_PRESETS.items())
            if identifier.isdigit():
                index = int(identifier) - 1
                if 0 <= index < len(personality_list):
                    personality_id = personality_list[index][0]
                else:
                    await self._send_reply(
                        msg,
                        f"编号 {identifier} 不存在\n\n"
                        f"当前有 {len(personality_list)} 个性格\n"
                        f"使用 /p 查看列表"
                    )
                    return
            else:
                if identifier in PERSONALITY_PRESETS:
                    personality_id = identifier
            
            if not personality_id:
                await self._send_reply(
                    msg,
                    f"性格 '{identifier}' 不存在\n\n"
                    f"使用 /p 查看可用性格"
                )
                return
            
            persona_config = {
                "ai_name": config_loader.config.persona.ai_name or "小C",
                "user_name": config_loader.config.persona.user_name or "用户",
                "user_address": getattr(config_loader.config.persona, 'user_address', '') or "",
                "personality": personality_id,
                "custom_personality": "",
            }
            
            session.session_persona_config = json.dumps(persona_config, ensure_ascii=False)
            session.use_custom_config = True
            await db.commit()
            
            preset = PERSONALITY_PRESETS[personality_id]
            await self._send_reply(
                msg,
                f"当前会话性格已设置为: {preset['name']}\n\n"
                f"{preset['description']}\n\n"
                f"此设置仅对当前会话生效"
            )


    async def _handle_provider_command(self, msg: InboundMessage, content: str) -> None:
        """处理 /provider 或 /m 命令 - 为当前会话设置模型提供商。
        
        用法:
        - /m                    查看可用提供商列表
        - /m 1                  使用编号切换（使用提供商默认模型）
        - /m 1 gpt-4           使用编号切换并指定模型名称
        - /m openai            使用ID切换（使用提供商默认模型）
        - /m openai gpt-4      使用ID切换并指定模型名称
        """
        from backend.modules.providers.registry import get_provider_metadata
        from backend.modules.providers.runtime import get_provider_runtime_state
        from backend.modules.config.loader import config_loader
        from backend.modules.session.runtime_config import (
            SESSION_MODEL_SOURCE_CHANNEL_COMMAND,
            resolve_session_runtime_config,
        )
        from sqlalchemy import select
        import json
        
        session_id = await self._get_or_create_session(msg)
        parts = content.split(maxsplit=2)
        
        async with self.db_session_factory() as db:
            result = await db.execute(select(Session).where(Session.id == session_id))
            session = result.scalar_one_or_none()
            
            if not session:
                await self._send_reply(msg, "会话不存在")
                return
            
            runtime_config = resolve_session_runtime_config(config_loader.config, session)
            current_provider = runtime_config.provider_name
            current_model = runtime_config.model_name
            is_custom_config = runtime_config.has_custom_model_config
            
            if len(parts) < 2:
                lines = ["已配置的模型提供商\n━━━━━━━━━━━━━━━━━━━━━━\n"]
                
                available_providers = []
                for provider_id, provider_config in config_loader.config.providers.items():
                    metadata = get_provider_metadata(provider_id)
                    runtime_state = get_provider_runtime_state(config_loader.config, provider_id)
                    if metadata and runtime_state.selectable:
                        available_providers.append((provider_id, metadata, provider_config))
                
                if not available_providers:
                    await self._send_reply(
                        msg,
                        "暂无已配置的提供商\n\n"
                        "请在 Web 界面配置 API Key"
                    )
                    return
                
                for i, (provider_id, metadata, provider_config) in enumerate(available_providers, 1):
                    is_current = provider_id == current_provider
                    marker = " ✓" if is_current else ""
                    lines.append(f"[{i}] {provider_id} - {metadata.name}{marker}")
                    
                    default_model = provider_config.model or metadata.default_model
                    if default_model:
                        lines.append(f"    默认: {default_model}")
                    
                    if is_current and current_model and current_model != default_model:
                        lines.append(f"    当前: {current_model} (自定义)")
                
                lines.append("\n━━━━━━━━━━━━━━━━━━━━━━")
                lines.append("当前会话配置:")
                if current_provider and current_model:
                    config_type = "自定义配置" if is_custom_config else "全局配置"
                    lines.append(f"  提供商: {current_provider}")
                    lines.append(f"  模型: {current_model}")
                    lines.append(f"  类型: {config_type}")
                else:
                    lines.append("  未配置")
                lines.append("\n使用方式:")
                lines.append("  /m <编号|ID>              使用默认模型")
                lines.append("  /m <编号|ID> <模型名>     指定模型名称")
                lines.append("\n示例:")
                lines.append("  /m 1                      使用第1个提供商的默认模型")
                lines.append("  /m 1 gpt-4               使用第1个提供商的 gpt-4")
                lines.append("  /m openai gpt-3.5-turbo  使用 openai 的 gpt-3.5-turbo")
                await self._send_reply(msg, "\n".join(lines))
                return
            
            identifier = parts[1].strip().lower()
            custom_model = parts[2].strip() if len(parts) > 2 else None
            
            available_providers = []
            for provider_id, provider_config in config_loader.config.providers.items():
                metadata = get_provider_metadata(provider_id)
                runtime_state = get_provider_runtime_state(config_loader.config, provider_id)
                if metadata and runtime_state.selectable:
                    available_providers.append((provider_id, metadata, provider_config))
            
            provider_id = None
            metadata = None
            provider_config = None
            
            if identifier.isdigit():
                index = int(identifier) - 1
                if 0 <= index < len(available_providers):
                    provider_id, metadata, provider_config = available_providers[index]
                else:
                    await self._send_reply(
                        msg,
                        f"编号 {identifier} 不存在\n\n"
                        f"当前有 {len(available_providers)} 个提供商\n"
                        f"使用 /m 查看列表"
                    )
                    return
            else:
                metadata = get_provider_metadata(identifier)
                if metadata:
                    provider_config = config_loader.config.providers.get(identifier)
                    if provider_config and get_provider_runtime_state(config_loader.config, identifier).selectable:
                        provider_id = identifier
            
            if not provider_id or not metadata or not provider_config:
                await self._send_reply(
                    msg,
                    f"提供商 '{identifier}' 不存在或未配置\n\n"
                    f"使用 /m 查看可用提供商"
                )
                return
            
            model_name = custom_model if custom_model else (provider_config.model or metadata.default_model)
            
            if not model_name:
                await self._send_reply(
                    msg,
                    f"无法确定模型名称\n\n"
                    f"请指定模型名称:\n"
                    f"/m {identifier} <模型名>\n\n"
                    f"例如: /m {identifier} gpt-4"
                )
                return
            
            runtime_state = get_provider_runtime_state(config_loader.config, provider_id)
            api_key = runtime_state.api_key
            if runtime_state.requires_api_key and not api_key:
                await self._send_reply(
                    msg,
                    f"提供商 '{provider_id}' 缺少 API 密钥\n\n"
                    f"请在 Web 界面配置 API Key"
                )
                return
            
            # 只持久化 provider/model：运行时 resolve_session_runtime_config
            # 并不读取 api_key/api_base（密钥始终在运行时从 provider 配置解析），
            # 把它们写进 session_model_config 只是明文落库的泄漏面，
            # 且 Web 端轮换密钥后此处会残留旧值。
            # source 标记是「用户显式设置会话模型」的凭据：没有标记的历史绑定会被
            # resolve_session_runtime_config 视为失效、回落全局默认模型。
            model_config = {
                "provider": provider_id,
                "model": model_name,
                "source": SESSION_MODEL_SOURCE_CHANNEL_COMMAND,
            }
            
            session.session_model_config = json.dumps(model_config, ensure_ascii=False)
            session.use_custom_config = True
            await db.commit()
            
            custom_note = " (自定义)" if custom_model else ""
            await self._send_reply(
                msg,
                f"当前会话模型已设置为:\n\n"
                f"提供商: {metadata.name}\n"
                f"模型: {model_name}{custom_note}\n\n"
                f"此设置仅对当前会话生效"
            )


    async def _handle_route_command(self, msg: InboundMessage, content: str) -> None:
        """处理 /route 命令。"""
        parts = content.strip().split(maxsplit=1)
        current_mode, current_profile = self._get_routing_preferences(msg)

        if len(parts) == 1:
            await self._send_reply(
                msg,
                "当前聊天路由模式:\n\n"
                f"- 模式: {current_mode}\n"
                f"- 外部代理: {current_profile or '未设置'}\n\n"
                "用法:\n"
                "- /route ai\n"
                "- /route direct\n"
                "- /route default",
            )
            return

        value = parts[1].strip().lower()
        key = self._get_route_preference_key(msg)

        if value == "default":
            self._route_mode_overrides.pop(key, None)
            resolved_mode, resolved_profile = self._get_routing_preferences(msg)
            await self._send_reply(
                msg,
                "当前聊天已恢复为渠道默认路由设置。\n\n"
                f"- 模式: {resolved_mode}\n"
                f"- 外部代理: {resolved_profile or '未设置'}",
            )
            return

        if value not in {"ai", "direct"}:
            await self._send_reply(
                msg,
                "无效路由模式。\n\n"
                "可用值:\n"
                "- /route ai\n"
                "- /route direct\n"
                "- /route default",
            )
            return

        self._route_mode_overrides[key] = value
        await self._send_reply(
            msg,
            "当前聊天路由模式已更新。\n\n"
            f"- 模式: {value}\n"
            f"- 外部代理: {current_profile or '未设置'}",
        )


    async def _handle_coder_command(self, msg: InboundMessage, content: str) -> None:
        """处理 /coder 命令。"""
        parts = content.strip().split(maxsplit=1)
        current_mode, current_profile = self._get_routing_preferences(msg)
        external_tool = self.tool_registry.get_tool("external_coding_agent")
        registry = getattr(external_tool, "registry", None)
        enabled_profiles = registry.enabled_profile_names() if registry else []
        enabled_profiles_text = ", ".join(enabled_profiles) if enabled_profiles else "无"

        if len(parts) == 1:
            await self._send_reply(
                msg,
                "当前聊天外部编程代理设置:\n\n"
                f"- 当前模式: {current_mode}\n"
                f"- 当前代理: {current_profile or '未设置'}\n"
                f"- 已启用 profile: {enabled_profiles_text}\n\n"
                "用法:\n"
                "- /coder codex\n"
                "- /coder claude\n"
                "- /coder default",
            )
            return

        value = parts[1].strip()
        key = self._get_route_preference_key(msg)

        if value.lower() == "default":
            self._coder_profile_overrides.pop(key, None)
            resolved_mode, resolved_profile = self._get_routing_preferences(msg)
            await self._send_reply(
                msg,
                "当前聊天已恢复为渠道默认外部代理设置。\n\n"
                f"- 当前模式: {resolved_mode}\n"
                f"- 当前代理: {resolved_profile or '未设置'}",
            )
            return

        if registry is None:
            await self._send_reply(msg, "external_coding_agent 工具当前不可用。")
            return

        try:
            canonical_name = registry.resolve_profile_name(value)
            registry.resolve_profile(canonical_name)
        except Exception as e:
            await self._send_reply(
                msg,
                f"无法切换外部代理: {e}\n\n已启用 profile: {enabled_profiles_text}",
            )
            return

        self._coder_profile_overrides[key] = canonical_name
        await self._send_reply(
            msg,
            "当前聊天外部编程代理已更新。\n\n"
            f"- 当前模式: {current_mode}\n"
            f"- 当前代理: {canonical_name}",
        )


    async def _handle_help_command(self, msg: InboundMessage) -> None:
        """处理 /help 命令。"""
        help_text = (
            "可用命令\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "会话管理:\n"
            "  /new (/n) - 创建新会话\n"
            "  /list (/l) - 查看当前聊天最近10个会话\n"
            "  /all (/al) - 查看所有会话\n"
            "  /switch (/s) <编号|ID> - 切换最近一次列表中的会话\n"
            "  /clear (/c) - 清除当前会话历史\n\n"
            "个性化设置:\n"
            "  /personality (/p) [编号|ID] - 查看/切换性格\n"
            "  /provider (/m) [编号|ID] [模型] - 查看/切换模型\n\n"
            "渠道编程代理:\n"
            "  /route (/rt) [ai|direct|default] - 切换当前聊天路由模式\n"
            "  /coder (/cdr) [profile|default] - 切换当前聊天外部编程代理\n\n"
            "团队协作:\n"
            "  /team - 查看可用团队名称\n"
            "  /team <团队名> <任务> - 直接运行指定智能体团队\n\n"
            "控制:\n"
            "  /stop - 停止当前任务\n"
            "  /help (/h) - 显示此帮助\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "提示:\n"
            "- 直接发消息即可对话\n"
            "- 括号内为命令简写\n"
            "- /l 查看当前聊天，/al 查看所有会话\n"
            "- 使用 /m 或 /p 查看详细用法\n"
            "- /route direct 后，普通消息会直接转发给外部编程代理\n"
            "- /coder codex 可把当前聊天的直通代理切到 codex\n"
            "- 先发送 /team 可查看当前可用团队名称\n"
            "- /team 文档深度分析 请总结这份文档，可直接执行团队工作流\n"
            "- 也可以直接说“用 codex 帮我修这个报错”或“用 claude 写个爬虫”\n"
        )
        await self._send_reply(msg, help_text)


    async def _handle_team_command(
        self,
        msg: InboundMessage,
        content: str,
        *,
        session_route: Dict[str, object],
        user_message_context: dict,
        cancel_token: CancellationToken,
        tool_event_handler=None,
        start_time: Optional[float] = None,
    ) -> None:
        """处理渠道 /team 命令，直接执行指定团队工作流。"""
        if content.strip() == "/team":
            await self._send_reply(
                msg,
                build_team_command_overview(
                    self.context_builder,
                    log_scope="channel team command",
                ),
            )
            return

        resolved = resolve_explicit_team_command(
            self.context_builder,
            content,
            log_scope="channel team command",
        )
        if resolved is None:
            await self._send_reply(msg, "团队命令当前不可用，请稍后重试。")
            return

        team_name, goal = resolved
        if not team_name:
            await self._send_reply(
                msg,
                build_team_command_overview(
                    self.context_builder,
                    log_scope="channel team command",
                ),
            )
            return
        if not goal:
            await self._send_reply(msg, build_team_goal_usage(team_name))
            return

        session_id = await self._get_or_create_session(msg)
        # 团队工作流会在同一会话里连跑多个子代理，必须与普通对话串行，
        # 否则子代理与主循环会同时写同一份会话历史。
        gate = get_session_gate()
        turn_acquired = False
        # finally 无条件引用 workflow_tool，必须在进入 try 前初始化，
        # 否则早期异常会触发 UnboundLocalError 并跳过 gate.release 等清理
        workflow_tool = None
        if gate.is_busy(session_id):
            await self._send_reply(msg, "当前会话还有任务在执行，请等它结束后再试。")
            return
        try:
            # acquire 与后续注册都必须在本 try 内，获取执行权后任何异常
            # 都能被 finally 兜住释放，避免会话被永久占用。
            await gate.acquire(session_id)
            turn_acquired = True
            self._active_tasks[session_id] = cancel_token
            self.tool_registry.set_message_context(
                {
                    "channel": msg.channel,
                    "sender_id": msg.sender_id,
                    "chat_id": msg.chat_id,
                    "metadata": msg.metadata,
                }
            )
            self.tool_registry.set_session_id(session_id)
            self.tool_registry.set_cancel_token(cancel_token)

            workflow_tool = self.tool_registry.get_tool("workflow_run")
            if workflow_tool and hasattr(workflow_tool, "set_event_callback"):
                workflow_tool.set_event_callback(tool_event_handler)

            await self._save_message(
                session_id,
                "user",
                content,
                message_context=user_message_context,
            )

            response = await self.tool_registry.execute(
                "workflow_run",
                {
                    "team_name": team_name,
                    "goal": goal,
                },
            )

            async with self.db_session_factory() as db:
                from backend.modules.session.manager import SessionManager

                session_manager = SessionManager(db)
                assistant_message = await session_manager.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=response,
                    message_context=_encode_message_context(
                        self._build_assistant_message_context(msg, session_route)
                    ),
                )

                try:
                    from backend.modules.tools.conversation_history import get_conversation_history

                    conversation_history = get_conversation_history()
                    updated_count = await conversation_history.backfill_message_id(
                        session_id=session_id,
                        message_id=assistant_message.id,
                    )
                    if updated_count > 0:
                        logger.info(
                            f"[{msg.channel}] Backfilled message_id={assistant_message.id} "
                            f"to {updated_count} team command tool conversations"
                        )
                except Exception as e:
                    logger.warning(f"[{msg.channel}] Failed to backfill team command message_id: {e}")

            channel_response = _WORKFLOW_META_RE.sub("", response).strip()
            await self._send_reply(msg, channel_response or response)

            duration = time.time() - start_time if start_time is not None else 0.0
            logger.info(
                f"[{msg.channel}] Team command handled for session {session_id} "
                f"(team={team_name}) in {duration:.2f}s"
            )
        finally:
            if workflow_tool and hasattr(workflow_tool, "set_event_callback"):
                workflow_tool.set_event_callback(None)
            self.tool_registry.set_cancel_token(None)
            self.tool_registry.set_message_context(None)
            self._active_tasks.pop(session_id, None)
            if turn_acquired:
                get_session_gate().release(session_id)


