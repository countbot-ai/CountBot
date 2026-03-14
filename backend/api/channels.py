"""渠道管理 API 端点"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Any, Dict, Optional
from loguru import logger

from backend.modules.config.loader import config_loader
from backend.modules.channels.manager import ChannelManager

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


@router.get("/list")
async def list_channels():
    """获取所有可用渠道列表"""
    try:
        config = config_loader.config
        channels_config = config.channels
        
        # 可用的渠道类型
        available_channels = {
            "telegram": {
                "name": "Telegram",
                "description": "Telegram messaging platform",
                "icon": "telegram",
                "enabled": channels_config.telegram.enabled if hasattr(channels_config, 'telegram') else False,
                "configured": bool(channels_config.telegram.token) if hasattr(channels_config, 'telegram') else False,
                "config": {
                    "token": (channels_config.telegram.token[:10] + "...") if (hasattr(channels_config, 'telegram') and channels_config.telegram.token) else "",
                    "proxy": channels_config.telegram.proxy if hasattr(channels_config, 'telegram') else None,
                    "allow_from": channels_config.telegram.allow_from if hasattr(channels_config, 'telegram') else []
                }
            },
            "discord": {
                "name": "Discord",
                "description": "Discord messaging platform",
                "icon": "discord",
                "enabled": channels_config.discord.enabled if hasattr(channels_config, 'discord') else False,
                "configured": bool(channels_config.discord.token) if hasattr(channels_config, 'discord') else False,
                "config": {
                    "token": (channels_config.discord.token[:10] + "...") if (hasattr(channels_config, 'discord') and channels_config.discord.token) else "",
                    "allow_from": channels_config.discord.allow_from if hasattr(channels_config, 'discord') else []
                }
            },
            "qq": {
                "name": "QQ",
                "description": "QQ messaging platform",
                "icon": "qq",
                "enabled": channels_config.qq.enabled if hasattr(channels_config, 'qq') else False,
                "configured": bool(channels_config.qq.app_id and channels_config.qq.secret) if hasattr(channels_config, 'qq') else False,
                "config": {
                    "app_id": (channels_config.qq.app_id[:8] + "...") if (hasattr(channels_config, 'qq') and channels_config.qq.app_id) else "",
                    "secret": "***" if (hasattr(channels_config, 'qq') and channels_config.qq.secret) else "",
                    "allow_from": channels_config.qq.allow_from if hasattr(channels_config, 'qq') else []
                }
            },
            "dingtalk": {
                "name": "DingTalk",
                "description": "DingTalk messaging platform",
                "icon": "dingtalk",
                "enabled": channels_config.dingtalk.enabled if hasattr(channels_config, 'dingtalk') else False,
                "configured": bool(channels_config.dingtalk.client_id and channels_config.dingtalk.client_secret) if hasattr(channels_config, 'dingtalk') else False,
                "config": {
                    "client_id": (channels_config.dingtalk.client_id[:8] + "...") if (hasattr(channels_config, 'dingtalk') and channels_config.dingtalk.client_id) else "",
                    "client_secret": "***" if (hasattr(channels_config, 'dingtalk') and channels_config.dingtalk.client_secret) else "",
                    "allow_from": channels_config.dingtalk.allow_from if hasattr(channels_config, 'dingtalk') else []
                }
            },
            "feishu": {
                "name": "Feishu",
                "description": "Feishu/Lark messaging platform",
                "icon": "feishu",
                "enabled": channels_config.feishu.enabled if hasattr(channels_config, 'feishu') else False,
                "configured": bool(channels_config.feishu.app_id and channels_config.feishu.app_secret) if hasattr(channels_config, 'feishu') else False,
                "config": {
                    "app_id": (channels_config.feishu.app_id[:8] + "...") if (hasattr(channels_config, 'feishu') and channels_config.feishu.app_id) else "",
                    "app_secret": "***" if (hasattr(channels_config, 'feishu') and channels_config.feishu.app_secret) else "",
                    "encrypt_key": "***" if (hasattr(channels_config, 'feishu') and channels_config.feishu.encrypt_key) else "",
                    "verification_token": "***" if (hasattr(channels_config, 'feishu') and channels_config.feishu.verification_token) else "",
                    "allow_from": channels_config.feishu.allow_from if hasattr(channels_config, 'feishu') else []
                }
            },
            "weibo": {
                "name": "Weibo",
                "description": "Weibo messaging platform",
                "icon": "weibo",
                "enabled": channels_config.weibo.enabled if hasattr(channels_config, 'weibo') else False,
                "configured": bool(channels_config.weibo.app_id and channels_config.weibo.app_secret) if hasattr(channels_config, 'weibo') else False,
                "config": {
                    "app_id": (channels_config.weibo.app_id[:8] + "...") if (hasattr(channels_config, 'weibo') and channels_config.weibo.app_id) else "",
                    "app_secret": "***" if (hasattr(channels_config, 'weibo') and channels_config.weibo.app_secret) else "",
                    "allow_from": channels_config.weibo.allow_from if hasattr(channels_config, 'weibo') else []
                }
            },
            "wecom": {
                "name": "WeCom",
                "description": "Enterprise WeChat messaging platform",
                "icon": "wecom",
                "enabled": channels_config.wecom.enabled if hasattr(channels_config, 'wecom') else False,
                "configured": bool(channels_config.wecom.bot_id and channels_config.wecom.secret) if hasattr(channels_config, 'wecom') else False,
                "config": {
                    "bot_id": (channels_config.wecom.bot_id[:8] + "...") if (hasattr(channels_config, 'wecom') and channels_config.wecom.bot_id) else "",
                    "secret": "***" if (hasattr(channels_config, 'wecom') and channels_config.wecom.secret) else "",
                    "websocket_url": channels_config.wecom.websocket_url if hasattr(channels_config, 'wecom') else "wss://openws.work.weixin.qq.com",
                    "allow_from": channels_config.wecom.allow_from if hasattr(channels_config, 'wecom') else []
                }
            },
            "xiaozhi": {
                "name": "小智AI",
                "description": "小智机器人 MCP 接入（工具调用/对话模式）",
                "icon": "xiaozhi",
                "enabled": channels_config.xiaozhi.enabled if hasattr(channels_config, 'xiaozhi') else False,
                "configured": bool(channels_config.xiaozhi.endpoint) if hasattr(channels_config, 'xiaozhi') else False,
                "config": {
                    "endpoint": channels_config.xiaozhi.endpoint if hasattr(channels_config, 'xiaozhi') else "",
                    "enable_conversation": channels_config.xiaozhi.enable_conversation if hasattr(channels_config, 'xiaozhi') else False,
                    "allow_from": channels_config.xiaozhi.allow_from if hasattr(channels_config, 'xiaozhi') else []
                }
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
        
        if request.config:
            logger.info(f"Testing {request.channel} with temporary config")
            
            # 创建临时配置对象
            from backend.modules.config.schema import (
                QQConfig, FeishuConfig, DingTalkConfig,
                TelegramConfig, DiscordConfig, WeiboConfig, WeComConfig
            )
            
            from backend.modules.config.schema import (
                QQConfig, FeishuConfig, DingTalkConfig,
                TelegramConfig, DiscordConfig, WeiboConfig, WeComConfig,
                XiaozhiConfig,
            )
            config_classes = {
                "qq": QQConfig,
                "feishu": FeishuConfig,
                "dingtalk": DingTalkConfig,
                "telegram": TelegramConfig,
                "discord": DiscordConfig,
                "weibo": WeiboConfig,
                "wecom": WeComConfig,
                "xiaozhi": XiaozhiConfig,
            }

            if request.channel not in config_classes:
                return {
                    "success": False,
                    "message": f"不支持的渠道: {request.channel}"
                }

            temp_config = config_classes[request.channel](**request.config)

            from backend.modules.channels.qq import QQChannel
            from backend.modules.channels.feishu import FeishuChannel
            from backend.modules.channels.dingtalk import DingTalkChannel
            from backend.modules.channels.telegram import TelegramChannel
            from backend.modules.channels.weibo import WeiboChannel
            from backend.modules.channels.wecom import WeComChannel
            from backend.modules.channels.xiaozhi import XiaozhiChannel

            channel_classes = {
                "qq": QQChannel,
                "feishu": FeishuChannel,
                "dingtalk": DingTalkChannel,
                "telegram": TelegramChannel,
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
            result = await manager.test_channel(request.channel)
        
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
                "Successfully authenticated with WeCom API": "成功通过企业微信 API 认证"
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



@router.post("/update")
async def update_channel_config(request: ChannelConfigUpdate, fastapi_request: Request):
    """更新渠道配置"""
    try:
        config = config_loader.config
        
        # 支持的渠道列表
        supported_channels = ["telegram", "discord", "qq", "dingtalk", "feishu", "weibo", "wecom", "xiaozhi"]
        
        if request.channel not in supported_channels:
            raise HTTPException(status_code=400, detail=f"Unknown channel: {request.channel}")
        
        # 获取渠道配置对象
        channel_config = getattr(config.channels, request.channel, None)
        if not channel_config:
            raise HTTPException(status_code=404, detail=f"Channel configuration not found: {request.channel}")
        
        for key, value in request.config.items():
            if hasattr(channel_config, key):
                setattr(channel_config, key, value)
            else:
                logger.warning(f"Unknown config key '{key}' for channel {request.channel}")
        
        # 保存配置
        await config_loader.save()
        
        # 重新加载配置到 message_handler
        try:
            if hasattr(fastapi_request.app.state, 'message_handler'):
                message_handler = fastapi_request.app.state.message_handler
                message_handler.reload_config()
                # 重新注册工具（含 xiaozhi send_message 的条件注册）
                channel_manager = getattr(fastapi_request.app.state, 'channel_manager', None)
                if channel_manager is not None:
                    message_handler.set_channel_manager(channel_manager)
                logger.info(f"Reloaded message handler config after updating {request.channel}")
        except Exception as e:
            logger.warning(f"Failed to reload message handler config: {e}")
        
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
        supported_channels = ["telegram", "discord", "qq", "dingtalk", "feishu", "weibo", "wecom", "xiaozhi"]

        if channel not in supported_channels:
            raise HTTPException(status_code=404, detail=f"Channel not found: {channel}")

        channel_config = getattr(config.channels, channel, None)

        if not channel_config:
            logger.warning(f"Channel configuration not found for {channel}, creating default")
            from backend.modules.config.schema import (
                TelegramConfig, DiscordConfig, QQConfig,
                DingTalkConfig, FeishuConfig, WeiboConfig, WeComConfig, XiaozhiConfig
            )
            config_classes = {
                "telegram": TelegramConfig, "discord": DiscordConfig,
                "qq": QQConfig, "dingtalk": DingTalkConfig,
                "feishu": FeishuConfig, "weibo": WeiboConfig,
                "wecom": WeComConfig, "xiaozhi": XiaozhiConfig,
            }
            channel_config = config_classes[channel]()
            setattr(config.channels, channel, channel_config)
            await config_loader.save()

        config_dict = {
            "enabled": channel_config.enabled,
            "allow_from": getattr(channel_config, "allow_from", [])
        }

        if channel == "telegram":
            config_dict.update({"token": channel_config.token, "proxy": getattr(channel_config, "proxy", None)})
        elif channel == "discord":
            config_dict.update({"token": channel_config.token})
        elif channel == "qq":
            config_dict.update({"app_id": channel_config.app_id, "secret": channel_config.secret})
        elif channel == "dingtalk":
            config_dict.update({"client_id": channel_config.client_id, "client_secret": channel_config.client_secret})
        elif channel == "feishu":
            config_dict.update({
                "app_id": channel_config.app_id, "app_secret": channel_config.app_secret,
                "encrypt_key": getattr(channel_config, "encrypt_key", ""),
                "verification_token": getattr(channel_config, "verification_token", "")
            })
        elif channel == "weibo":
            config_dict.update({"app_id": channel_config.app_id, "app_secret": channel_config.app_secret})
        elif channel == "wecom":
            config_dict.update({
                "bot_id": channel_config.bot_id, "secret": channel_config.secret,
                "websocket_url": getattr(channel_config, "websocket_url", "wss://openws.work.weixin.qq.com")
            })
        elif channel == "xiaozhi":
            config_dict.update({
                "endpoint": channel_config.endpoint,
                "enable_conversation": channel_config.enable_conversation,
            })
        
        return {
            "success": True,
            "config": config_dict
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting channel config: {e}")
        raise HTTPException(status_code=500, detail=str(e))
