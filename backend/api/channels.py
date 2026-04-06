"""渠道管理 API 端点"""

import asyncio
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Any, Dict, Optional
from loguru import logger

from backend.modules.config.loader import config_loader
from backend.modules.channels.manager import ChannelManager
from backend.modules.external_agents.registry import ExternalAgentRegistry

router = APIRouter(prefix="/api/channels", tags=["channels"])

# 全局渠道管理器实例（将在应用启动时初始化）
_channel_manager: Optional[ChannelManager] = None


def set_channel_manager(manager: ChannelManager):
    """设置全局渠道管理器实例"""
    global _channel_manager
    _channel_manager = manager


def get_channel_manager() -> ChannelManager:
    """获取渠道管理器实例"""
    if _channel_manager is None:
        raise HTTPException(status_code=500, detail="Channel manager not initialized")
    return _channel_manager


class ChannelConfigUpdate(BaseModel):
    """渠道配置更新请求"""
    channel: str
    config: Dict[str, Any]


class ChannelTestRequest(BaseModel):
    """渠道测试请求"""
    channel: str
    config: Optional[Dict[str, Any]] = None  # 可选的临时配置
    account_id: Optional[str] = None


class WeChatLoginStartRequest(BaseModel):
    """微信扫码登录启动请求。"""

    config: Optional[Dict[str, Any]] = None
    account_id: Optional[str] = None


class WeChatLoginPollRequest(BaseModel):
    """微信扫码登录轮询请求。"""

    session_key: str


def _mask_channel_secret(key: str, value: Any) -> Any:
    if value is None:
        return value
    lowered = key.lower()
    if lowered in {"token", "secret", "app_secret", "client_secret", "bot_id"}:
        text = str(value)
        if not text:
            return ""
        if lowered == "bot_id":
            return text[:8] + "..."
        if lowered == "token":
            return text[:10] + "..."
        return "***"
    if lowered in {"app_id", "client_id"}:
        text = str(value)
        return text[:8] + "..." if text else ""
    return value


def _normalize_accounts_payload(config_dict: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(config_dict)
    accounts = normalized.get("accounts", {}) or {}
    normalized["accounts"] = {
        str(account_id): {
            **dict(account_cfg),
            "account_id": str(account_id),
        }
        for account_id, account_cfg in accounts.items()
    }
    return normalized


def _serialize_channel_for_list(channel_config: Any) -> Dict[str, Any]:
    config_dict = _normalize_accounts_payload(channel_config.model_dump())
    accounts = config_dict.get("accounts", {}) or {}
    enabled = bool(config_dict.get("enabled")) or any(
        bool(account_cfg.get("enabled"))
        for account_cfg in accounts.values()
    )
    visible_config = {
        key: _mask_channel_secret(key, value)
        for key, value in config_dict.items()
        if key != "accounts"
    }
    visible_accounts = {
        account_id: {
            key: _mask_channel_secret(key, value)
            for key, value in account_cfg.items()
        }
        for account_id, account_cfg in accounts.items()
    }

    return {
        "enabled": enabled,
        "configured": any(
            bool(account_cfg.get(field))
            for account_cfg in [config_dict, *accounts.values()]
            for field in ("token", "app_id", "client_id", "bot_id", "endpoint")
        ),
        "config": {
            **visible_config,
            "accounts": visible_accounts,
            "account_count": (1 if any(config_dict.get(field) for field in ("token", "app_id", "client_id", "bot_id", "endpoint")) else 0) + len(visible_accounts),
        },
    }


def _select_account_config(channel_config: Any, account_id: Optional[str]) -> Any:
    config_dict = _normalize_accounts_payload(channel_config.model_dump())
    selected_account_id = str(account_id or config_dict.get("account_id") or "default")
    top_level_account_id = str(config_dict.get("account_id") or "default")
    accounts = config_dict.get("accounts", {}) or {}

    if selected_account_id == top_level_account_id:
        return channel_config.__class__(**{**config_dict, "accounts": {}, "account_id": top_level_account_id})

    account_cfg = accounts.get(selected_account_id)
    if account_cfg is None:
        if accounts:
            raise ValueError(f"机器人账号不存在: {selected_account_id}")
        return channel_config.__class__(**{**config_dict, "accounts": {}, "account_id": selected_account_id})

    merged_data = {
        **config_dict,
        **account_cfg,
        "accounts": {},
        "account_id": selected_account_id,
    }
    return channel_config.__class__(**merged_data)


_CHANNEL_UNIQUE_ID_FIELDS: Dict[str, tuple[str, ...]] = {
    "telegram": ("token",),
    "qq": ("app_id",),
    "wechat": ("login_bot_id",),
    "dingtalk": ("client_id",),
    "feishu": ("app_id",),
    "weibo": ("app_id",),
    "wecom": ("bot_id",),
}


def _validate_duplicate_accounts(channel_name: str, channel_config: Any) -> None:
    """校验多机器人配置中是否复用了同一物理机器人身份。"""
    unique_fields = _CHANNEL_UNIQUE_ID_FIELDS.get(channel_name)
    if not unique_fields:
        return

    config_dict = _normalize_accounts_payload(channel_config.model_dump())
    seen: Dict[str, str] = {}

    def build_signature(account_cfg: Dict[str, Any]) -> Optional[str]:
        parts = []
        for field in unique_fields:
            value = str(account_cfg.get(field) or "").strip()
            if not value:
                return None
            parts.append(f"{field}={value}")
        return "|".join(parts)

    accounts_to_check = [
        (str(config_dict.get("account_id") or "default"), config_dict),
        *[
            (str(account_id), dict(account_cfg))
            for account_id, account_cfg in (config_dict.get("accounts", {}) or {}).items()
        ],
    ]

    for account_id, account_cfg in accounts_to_check:
        signature = build_signature(account_cfg)
        if not signature:
            continue
        previous_account = seen.get(signature)
        if previous_account is not None:
            fields_text = ", ".join(unique_fields)
            raise ValueError(
                f"检测到重复机器人配置：账号 '{account_id}' 与 '{previous_account}' 使用相同的 {fields_text}。"
                "同一个物理机器人不能重复配置为多个账号。"
            )
        seen[signature] = account_id


def _validate_external_coding_route_config(channel_name: str, channel_config: Any) -> None:
    """校验渠道账号的外部编程工具路由配置。"""
    workspace = Path(config_loader.config.workspace.path).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    registry = ExternalAgentRegistry(workspace=workspace)

    config_dict = _normalize_accounts_payload(channel_config.model_dump())
    accounts_to_check = [
        (str(config_dict.get("account_id") or "default"), config_dict),
        *[
            (str(account_id), dict(account_cfg))
            for account_id, account_cfg in (config_dict.get("accounts", {}) or {}).items()
        ],
    ]

    for account_id, account_cfg in accounts_to_check:
        route_mode = str(account_cfg.get("routing_mode", "ai") or "ai").strip().lower()
        if route_mode not in {"ai", "direct"}:
            raise ValueError(
                f"{channel_name} 渠道账号 '{account_id}' 的路由模式无效: {route_mode}"
            )

        profile_name = str(account_cfg.get("external_coding_profile", "") or "").strip()
        if route_mode == "direct" and not profile_name:
            raise ValueError(
                f"{channel_name} 渠道账号 '{account_id}' 处于直通模式时，必须设置默认外部编程工具。"
            )

        if profile_name:
            try:
                registry.resolve_profile(profile_name)
            except Exception as exc:
                raise ValueError(
                    f"{channel_name} 渠道账号 '{account_id}' 的外部编程工具不可用: {exc}"
                ) from exc


async def _restart_channel_manager(fastapi_request: Request) -> Optional[ChannelManager]:
    """基于最新配置热重建渠道管理器。"""
    app_state = fastapi_request.app.state
    old_manager = getattr(app_state, "channel_manager", None)
    old_task = getattr(app_state, "channel_manager_task", None)
    message_queue = getattr(app_state, "message_queue", None)

    if message_queue is None:
        logger.warning("Skip channel manager reload: message_queue missing")
        return old_manager

    if old_manager is not None:
        await old_manager.stop_all()

    if old_task is not None:
        try:
            await asyncio.wait_for(old_task, timeout=5)
        except asyncio.TimeoutError:
            old_task.cancel()
            await asyncio.gather(old_task, return_exceptions=True)
        except asyncio.CancelledError:
            pass

    manager = ChannelManager(config_loader.config, message_queue)
    app_state.channel_manager = manager
    set_channel_manager(manager)

    message_handler = getattr(app_state, "message_handler", None)
    if message_handler is not None:
        message_handler.set_channel_manager(manager)

    cron_executor = getattr(app_state, "cron_executor", None)
    if cron_executor is not None:
        cron_executor.channel_manager = manager

    shared = getattr(app_state, "shared", None)
    if isinstance(shared, dict):
        tool_params = shared.get("tool_params")
        if isinstance(tool_params, dict):
            try:
                from backend.modules.tools.setup import register_all_tools

                tool_params["channel_manager"] = manager
                shared["tool_registry"] = register_all_tools(
                    **tool_params,
                    memory_store=shared.get("memory"),
                )
                cron_agent = getattr(cron_executor, "agent", None)
                if cron_agent is not None:
                    cron_agent.tools = register_all_tools(
                        **tool_params,
                        memory_store=shared.get("memory"),
                    )
                logger.info("Shared tool registry synced with reloaded channel manager")
            except Exception as exc:
                logger.warning(f"Failed to sync shared tool registry after channel reload: {exc}")

    background_tasks = getattr(app_state, "background_tasks", None)
    if isinstance(background_tasks, list) and old_task is not None:
        app_state.background_tasks = [
            task for task in background_tasks
            if task is not old_task and not task.done()
        ]
        background_tasks = app_state.background_tasks
    new_task = None
    if manager.enabled_channels:
        new_task = asyncio.create_task(manager.start_all())
        if isinstance(background_tasks, list):
            background_tasks.append(new_task)
    app_state.channel_manager_task = new_task

    logger.info(
        f"Reloaded channel manager with {len(manager.enabled_channels)} channel instance(s)"
    )
    return manager


@router.get("/list")
async def list_channels():
    """获取所有可用渠道列表"""
    try:
        config = config_loader.config
        channels_config = config.channels
        
        telegram_data = _serialize_channel_for_list(channels_config.telegram)
        discord_data = _serialize_channel_for_list(channels_config.discord)
        qq_data = _serialize_channel_for_list(channels_config.qq)
        wechat_data = _serialize_channel_for_list(channels_config.wechat)
        dingtalk_data = _serialize_channel_for_list(channels_config.dingtalk)
        feishu_data = _serialize_channel_for_list(channels_config.feishu)
        weibo_data = _serialize_channel_for_list(channels_config.weibo)
        wecom_data = _serialize_channel_for_list(channels_config.wecom)
        xiaozhi_data = _serialize_channel_for_list(channels_config.xiaozhi)

        available_channels = {
            "telegram": {
                "name": "Telegram",
                "description": "Telegram messaging platform",
                "icon": "telegram",
                **telegram_data,
            },
            "discord": {
                "name": "Discord",
                "description": "Discord messaging platform",
                "icon": "discord",
                **discord_data,
            },
            "qq": {
                "name": "QQ",
                "description": "QQ messaging platform",
                "icon": "qq",
                **qq_data,
            },
            "wechat": {
                "name": "微信",
                "description": "WeChat messaging platform",
                "icon": "wechat",
                **wechat_data,
            },
            "dingtalk": {
                "name": "钉钉",
                "description": "DingTalk messaging platform",
                "icon": "dingtalk",
                **dingtalk_data,
            },
            "feishu": {
                "name": "飞书",
                "description": "Feishu/Lark messaging platform",
                "icon": "feishu",
                **feishu_data,
            },
            "weibo": {
                "name": "微博",
                "description": "Weibo messaging platform",
                "icon": "weibo",
                **weibo_data,
            },
            "wecom": {
                "name": "企业微信",
                "description": "Enterprise WeChat messaging platform",
                "icon": "wecom",
                **wecom_data,
            },
            "xiaozhi": {
                "name": "小智AI",
                "description": "小智机器人 MCP 接入（工具调用/对话模式）",
                "icon": "xiaozhi",
                **xiaozhi_data,
            }
        }
        
        return {
            "success": True,
            "channels": available_channels
        }
    
    except Exception as e:
        logger.error(f"Error listing channels: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_channels_status():
    """获取所有渠道的运行状态"""
    try:
        manager = get_channel_manager()
        status = manager.get_status()
        
        return {
            "success": True,
            "status": status,
            "running": manager.is_running
        }
    
    except Exception as e:
        logger.error(f"Error getting channels status: {e}")
        return {
            "success": False,
            "status": {},
            "running": False,
            "error": str(e)
        }


@router.post("/test")
async def test_channel(request: ChannelTestRequest):
    """测试指定渠道的连接"""
    try:
        manager = get_channel_manager()
        account_id = str(request.account_id or "").strip() or None
        
        if request.config:
            logger.info(
                f"Testing {request.channel} with temporary config"
                f"{f' for account {account_id}' if account_id else ''}"
            )
            
            # 创建临时配置对象
            from backend.modules.config.schema import (
                QQConfig, FeishuConfig, DingTalkConfig,
                TelegramConfig, DiscordConfig, WeChatConfig, WeiboConfig, WeComConfig,
                XiaozhiConfig,
            )
            config_classes = {
                "qq": QQConfig,
                "feishu": FeishuConfig,
                "dingtalk": DingTalkConfig,
                "telegram": TelegramConfig,
                "discord": DiscordConfig,
                "wechat": WeChatConfig,
                "weibo": WeiboConfig,
                "wecom": WeComConfig,
                "xiaozhi": XiaozhiConfig,
            }

            if request.channel not in config_classes:
                return {
                    "success": False,
                    "message": f"不支持的渠道: {request.channel}"
                }

            temp_channel_config = config_classes[request.channel](
                **_normalize_accounts_payload(request.config)
            )
            _validate_duplicate_accounts(request.channel, temp_channel_config)
            temp_config = _select_account_config(temp_channel_config, account_id)

            from backend.modules.channels.qq import QQChannel
            from backend.modules.channels.feishu import FeishuChannel
            from backend.modules.channels.dingtalk import DingTalkChannel
            from backend.modules.channels.telegram import TelegramChannel
            from backend.modules.channels.wechat import WeChatChannel
            from backend.modules.channels.weibo import WeiboChannel
            from backend.modules.channels.wecom import WeComChannel
            from backend.modules.channels.xiaozhi import XiaozhiChannel

            channel_classes = {
                "qq": QQChannel,
                "feishu": FeishuChannel,
                "dingtalk": DingTalkChannel,
                "telegram": TelegramChannel,
                "wechat": WeChatChannel,
                "weibo": WeiboChannel,
                "wecom": WeComChannel,
                "xiaozhi": XiaozhiChannel,
            }
            
            if request.channel in channel_classes:
                temp_channel = channel_classes[request.channel](temp_config)
                result = await temp_channel.test_connection()
            else:
                return {
                    "success": False,
                    "message": f"渠道 {request.channel} 暂不支持测试功能"
                }
        else:
            # 使用已保存的配置测试
            result = await manager.test_channel(request.channel, account_id=account_id)
        
        # 翻译英文消息为中文
        message = result["message"]
        message_translations = {
            # QQ 渠道消息
            "App ID or Secret not configured": "App ID 或 Secret 未配置",
            "Invalid App ID format - App ID should be at least 8 characters": "App ID 格式无效 - 至少需要 8 个字符",
            "Invalid Secret format - Secret should be at least 16 characters": "Secret 格式无效 - 至少需要 16 个字符",
            "Invalid App ID format - QQ App ID should be numeric (e.g., 102848021234)": "App ID 格式无效 - QQ App ID 必须是纯数字（例如：102848021234）",
            "Invalid Secret format - Secret should contain only letters and numbers": "Secret 格式无效 - 只能包含字母和数字",
            "Configuration format validated successfully. Enable the channel to test the actual connection.": "配置格式验证通过。启用渠道后将进行实际连接测试。",
            "QQ credentials verified successfully - connection test passed": "QQ 凭据验证成功 - 连接测试通过",
            "Invalid App ID or Secret - credentials rejected by QQ": "App ID 或 Secret 无效 - QQ 拒绝了凭据",
            "Access denied - check your bot permissions at q.qq.com": "访问被拒绝 - 请在 q.qq.com 检查机器人权限",
            "Connection timeout - check your network connection or QQ API status": "连接超时 - 请检查网络连接或 QQ API 状态",
            "Network error - unable to reach QQ API": "网络错误 - 无法连接到 QQ API",
            "QQ SDK not installed. Run: pip install qq-botpy": "QQ SDK 未安装。运行: pip install qq-botpy",
            
            # 飞书渠道消息
            "App ID or App Secret not configured": "App ID 或 App Secret 未配置",
            "Invalid App ID format - Feishu App ID should start with 'cli_' (e.g., cli_a6d0...)": "App ID 格式无效 - 飞书 App ID 必须以 'cli_' 开头（例如：cli_a6d0...）",
            "Invalid App ID format - App ID is too short": "App ID 格式无效 - App ID 太短",
            "Invalid App Secret format - App Secret is too short": "App Secret 格式无效 - App Secret 太短",
            "Feishu credentials verified successfully - connection test passed": "飞书凭据验证成功 - 连接测试通过",
            "Invalid App ID or App Secret - credentials rejected by Feishu": "App ID 或 App Secret 无效 - 飞书拒绝了凭据",
            "Connection timeout - check your network connection": "连接超时 - 请检查网络连接",
            "Invalid App ID or App Secret - check your credentials at open.feishu.cn": "App ID 或 App Secret 无效 - 请在 open.feishu.cn 检查凭据",
            "Feishu SDK not installed. Run: pip install lark-oapi": "飞书 SDK 未安装。运行: pip install lark-oapi",
            
            # 钉钉渠道消息
            "Client ID or Client Secret not configured": "Client ID 或 Client Secret 未配置",
            "DingTalk SDK not installed": "钉钉 SDK 未安装",
            "DingTalk credentials verified successfully": "钉钉凭据验证成功",
            "Invalid Client ID or Client Secret": "Client ID 或 Client Secret 无效",
            
            # Telegram 渠道消息
            "Token not configured": "Token 未配置",
            "python-telegram-bot not installed": "python-telegram-bot 未安装",
            
            # 企业微信渠道消息
            "Bot ID or Secret not configured": "Bot ID 或 Secret 未配置",
            "Invalid Bot ID format - Bot ID should be at least 8 characters": "Bot ID 格式无效 - 至少需要 8 个字符",
            "Invalid Secret format - Secret should be at least 16 characters": "Secret 格式无效 - 至少需要 16 个字符",
            "Invalid Bot ID format - should contain only letters, numbers, hyphens and underscores": "Bot ID 格式无效 - 只能包含字母、数字、连字符和下划线",
            "Invalid Secret format - should contain only letters, numbers, hyphens and underscores": "Secret 格式无效 - 只能包含字母、数字、连字符和下划线",
            "Invalid WebSocket URL format - should start with ws:// or wss://": "WebSocket URL 格式无效 - 必须以 ws:// 或 wss:// 开头",
            "WeCom credentials verified successfully - connection test passed": "企业微信凭据验证成功 - 连接测试通过",
            "Invalid Bot ID or Secret - authentication failed (error code: 40001)": "Bot ID 或 Secret 无效 - 认证失败（错误码：40001）",
            "Invalid Bot ID or Secret - bot not found or disabled (error code: 40014)": "Bot ID 或 Secret 无效 - 机器人未找到或已禁用（错误码：40014）",
            "Invalid Bot ID - bot not found or incorrect format (error code: 93019)": "Bot ID 无效 - 机器人未找到或格式不正确（错误码：93019）",
            "Connection timeout - check your network connection or WeCom API status": "连接超时 - 请检查网络连接或企业微信 API 状态",
            "Invalid WebSocket URL - check the websocket_url configuration": "WebSocket URL 无效 - 请检查 websocket_url 配置",
            "Invalid response format from WeCom server": "企业微信服务器响应格式无效",
            "websockets library not installed. Run: pip install websockets": "websockets 库未安装。运行: pip install websockets",
        }
        
        # 翻译消息
        translated_message = message_translations.get(message, message)
        
        # 动态消息翻译（前缀匹配）
        if translated_message == message:
            if message.startswith("Connected to @"):
                bot_username = message[len("Connected to @"):]
                translated_message = f"已连接到 @{bot_username}"
            elif message.startswith("Connection failed:"):
                error_detail = message[len("Connection failed:"):].strip()
                # Flood control 友好提示
                import re
                flood_match = re.search(r"Flood control exceeded.*?Retry in (\d+)", error_detail)
                if flood_match:
                    seconds = int(flood_match.group(1))
                    minutes = seconds // 60
                    if minutes > 0:
                        translated_message = f"测试过于频繁，Telegram 暂时限制了请求，请 {minutes} 分钟后再试（不影响正常聊天）"
                    else:
                        translated_message = f"测试过于频繁，Telegram 暂时限制了请求，请 {seconds} 秒后再试（不影响正常聊天）"
                else:
                    translated_message = f"连接失败: {error_detail}"
            elif message.startswith("Invalid Bot ID or Secret - credentials rejected by WeCom:"):
                error_detail = message[len("Invalid Bot ID or Secret - credentials rejected by WeCom:"):].strip()
                translated_message = f"Bot ID 或 Secret 无效 - 企业微信拒绝了凭据: {error_detail}"
            elif message.startswith("Connection closed by server - check your Bot ID and Secret (code:"):
                import re
                code_match = re.search(r'\(code: (\w+)\)', message)
                if code_match:
                    code = code_match.group(1)
                    translated_message = f"服务器关闭连接 - 请检查 Bot ID 和 Secret（错误码：{code}）"
                else:
                    translated_message = "服务器关闭连接 - 请检查 Bot ID 和 Secret"
            elif message.startswith("Network error - unable to reach WeCom API:"):
                error_detail = message[len("Network error - unable to reach WeCom API:"):].strip()
                translated_message = f"网络错误 - 无法连接到企业微信 API: {error_detail}"
        
        # 翻译 note 字段
        if result.get("bot_info") and result["bot_info"].get("note"):
            note = result["bot_info"]["note"]
            note_translations = {
                "Full connection test will be performed when channel is enabled": "启用渠道后将进行完整连接测试",
                "Format check passed. Real connection test will be performed when channel is enabled.": "格式检查通过。启用渠道后将进行真实连接测试。",
                "Successfully obtained access token from Feishu API": "成功从飞书 API 获取访问令牌",
                "Successfully authenticated with QQ API": "成功通过 QQ API 认证",
                "Successfully authenticated with WeCom API": "成功通过企业微信 API 认证",
            }
            result["bot_info"]["note"] = note_translations.get(note, note)
        
        # 翻译 status 字段
        if result.get("bot_info") and result["bot_info"].get("status"):
            status = result["bot_info"]["status"]
            status_translations = {
                "configured": "已配置",
                "format_validated": "格式已验证",
                "credentials_verified": "凭据已验证",
                "connected": "已连接"
            }
            result["bot_info"]["status"] = status_translations.get(status, status)
        
        return {
            "success": result["success"],
            "message": translated_message,
            "data": result.get("bot_info")
        }
    
    except Exception as e:
        logger.error(f"Error testing channel {request.channel}: {e}")
        return {
            "success": False,
            "message": f"测试失败: {str(e)}"
        }


@router.post("/wechat/login/start")
async def start_wechat_login(request: WeChatLoginStartRequest):
    """启动微信扫码登录。"""
    try:
        from backend.modules.channels.wechat import start_wechat_qr_login
        from backend.modules.config.schema import WeChatConfig

        channel_config = WeChatConfig(
            **_normalize_accounts_payload(
                request.config or config_loader.config.channels.wechat.model_dump()
            )
        )
        account_id = str(request.account_id or "default").strip() or "default"
        resolved_config = _select_account_config(channel_config, account_id)

        result = await start_wechat_qr_login(
            account_id=account_id,
            base_url=str(getattr(resolved_config, "base_url", "") or ""),
            config_snapshot=channel_config.model_dump(),
        )
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"Failed to start wechat login: {e}")
        return {"success": False, "message": f"启动微信扫码登录失败: {e}"}


@router.post("/wechat/login/poll")
async def poll_wechat_login(request: WeChatLoginPollRequest, fastapi_request: Request):
    """轮询微信扫码登录状态。"""
    try:
        from backend.modules.channels.wechat import (
            clear_wechat_session_pause,
            poll_wechat_qr_login,
        )
        from backend.modules.config.schema import WeChatConfig

        result = await poll_wechat_qr_login(request.session_key)
        if not result.get("success") or result.get("status") != "confirmed":
            return result

        config_snapshot = result.get("config_snapshot") or config_loader.config.channels.wechat.model_dump()
        channel_config = WeChatConfig(**_normalize_accounts_payload(config_snapshot))
        account_id = str(result.get("account_id") or "default").strip() or "default"

        login_data = dict(result.get("result") or {})
        merged_channel_config = _normalize_accounts_payload(channel_config.model_dump())
        merged_channel_config["enabled"] = True
        accounts = merged_channel_config.get("accounts", {}) or {}
        top_level_account_id = str(merged_channel_config.get("account_id") or "default")

        if account_id == top_level_account_id:
            merged_channel_config["enabled"] = True
            merged_channel_config.update(login_data)
        else:
            account_payload = dict(accounts.get(account_id) or {})
            account_payload.update(login_data)
            account_payload["account_id"] = account_id
            account_payload["enabled"] = True
            accounts[account_id] = account_payload
            merged_channel_config["accounts"] = accounts

        clear_wechat_session_pause(account_id)
        config_loader.config.channels.wechat = WeChatConfig(**merged_channel_config)
        _validate_duplicate_accounts("wechat", config_loader.config.channels.wechat)
        _validate_external_coding_route_config("wechat", config_loader.config.channels.wechat)
        await config_loader.save()

        message_handler = getattr(fastapi_request.app.state, "message_handler", None)
        channel_manager = await _restart_channel_manager(fastapi_request)
        if message_handler is not None and channel_manager is not None:
            message_handler.set_channel_manager(channel_manager)

        return {
            "success": True,
            "status": "confirmed",
            "message": "微信连接成功",
            "account_id": account_id,
            "result": login_data,
            "config": _normalize_accounts_payload(config_loader.config.channels.wechat.model_dump()),
        }
    except Exception as e:
        logger.error(f"Failed to poll wechat login: {e}")
        return {"success": False, "message": f"轮询微信登录状态失败: {e}"}



@router.post("/update")
async def update_channel_config(request: ChannelConfigUpdate, fastapi_request: Request):
    """更新渠道配置"""
    try:
        config = config_loader.config
        
        # 支持的渠道列表
        supported_channels = ["telegram", "discord", "qq", "wechat", "dingtalk", "feishu", "weibo", "wecom", "xiaozhi"]
        
        if request.channel not in supported_channels:
            raise HTTPException(status_code=400, detail=f"Unknown channel: {request.channel}")
        
        channel_config = getattr(config.channels, request.channel, None)
        if not channel_config:
            raise HTTPException(status_code=404, detail=f"Channel configuration not found: {request.channel}")

        from backend.modules.config.schema import (
            TelegramConfig, DiscordConfig, QQConfig,
            WeChatConfig, DingTalkConfig, FeishuConfig, WeiboConfig, WeComConfig, XiaozhiConfig,
        )

        config_classes = {
            "telegram": TelegramConfig,
            "discord": DiscordConfig,
            "qq": QQConfig,
            "wechat": WeChatConfig,
            "dingtalk": DingTalkConfig,
            "feishu": FeishuConfig,
            "weibo": WeiboConfig,
            "wecom": WeComConfig,
            "xiaozhi": XiaozhiConfig,
        }

        merged_config = _normalize_accounts_payload(channel_config.model_dump())
        merged_config.update(request.config)
        merged_config = _normalize_accounts_payload(merged_config)
        setattr(
            config.channels,
            request.channel,
            config_classes[request.channel](**merged_config),
        )
        updated_channel_config = getattr(config.channels, request.channel)
        _validate_duplicate_accounts(request.channel, updated_channel_config)
        _validate_external_coding_route_config(request.channel, updated_channel_config)
        
        # 保存配置
        await config_loader.save()
        
        # 重新加载配置到 message_handler
        try:
            if hasattr(fastapi_request.app.state, 'message_handler'):
                message_handler = fastapi_request.app.state.message_handler
                message_handler.reload_config()
                channel_manager = await _restart_channel_manager(fastapi_request)
                if channel_manager is not None:
                    message_handler.set_channel_manager(channel_manager)
                logger.info(
                    f"Reloaded message handler and channel manager after updating {request.channel}"
                )
        except Exception as e:
            logger.warning(f"Failed to reload message handler/channel manager config: {e}")
        
        logger.info(f"Updated {request.channel} channel configuration")
        
        return {
            "success": True,
            "message": f"{request.channel} configuration updated successfully"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating channel config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{channel}/config")
async def get_channel_config(channel: str):
    """获取指定渠道的配置"""
    try:
        config = config_loader.config
        
        # 支持的渠道列表
        supported_channels = ["telegram", "discord", "qq", "wechat", "dingtalk", "feishu", "weibo", "wecom", "xiaozhi"]

        if channel not in supported_channels:
            raise HTTPException(status_code=404, detail=f"Channel not found: {channel}")

        channel_config = getattr(config.channels, channel, None)

        if not channel_config:
            logger.warning(f"Channel configuration not found for {channel}, creating default")
            from backend.modules.config.schema import (
                TelegramConfig, DiscordConfig, QQConfig, WeChatConfig,
                DingTalkConfig, FeishuConfig, WeiboConfig, WeComConfig, XiaozhiConfig
            )
            config_classes = {
                "telegram": TelegramConfig, "discord": DiscordConfig,
                "qq": QQConfig, "wechat": WeChatConfig, "dingtalk": DingTalkConfig,
                "feishu": FeishuConfig, "weibo": WeiboConfig,
                "wecom": WeComConfig, "xiaozhi": XiaozhiConfig,
            }
            channel_config = config_classes[channel]()
            setattr(config.channels, channel, channel_config)
            await config_loader.save()

        config_dict = _normalize_accounts_payload(channel_config.model_dump())
        
        return {
            "success": True,
            "config": config_dict
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting channel config: {e}")
        raise HTTPException(status_code=500, detail=str(e))
