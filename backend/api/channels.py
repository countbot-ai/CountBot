"""渠道管理 API 端点"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any
from loguru import logger

from backend.modules.config.loader import config_loader
from backend.modules.channels.manager import ChannelManager

router = APIRouter(prefix="/api/channels", tags=["channels"])

# 全局渠道管理器实例（将在应用启动时初始化）
_channel_manager: ChannelManager | None = None


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
    config: dict[str, Any]


class ChannelTestRequest(BaseModel):
    """渠道测试请求"""
    channel: str
    config: dict[str, Any] | None = None  # 可选的临时配置


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
            "wechat": {
                "name": "WeChat",
                "description": "WeChat messaging platform",
                "icon": "wechat",
                "enabled": channels_config.wechat.enabled if hasattr(channels_config, 'wechat') else False,
                "configured": bool(channels_config.wechat.app_id and channels_config.wechat.app_secret) if hasattr(channels_config, 'wechat') else False,
                "config": {
                    "app_id": (channels_config.wechat.app_id[:8] + "...") if (hasattr(channels_config, 'wechat') and channels_config.wechat.app_id) else "",
                    "app_secret": "***" if (hasattr(channels_config, 'wechat') and channels_config.wechat.app_secret) else "",
                    "allow_from": channels_config.wechat.allow_from if hasattr(channels_config, 'wechat') else []
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
                TelegramConfig, DiscordConfig, WeChatConfig
            )
            
            config_classes = {
                "qq": QQConfig,
                "feishu": FeishuConfig,
                "dingtalk": DingTalkConfig,
                "telegram": TelegramConfig,
                "discord": DiscordConfig,
                "wechat": WeChatConfig
            }
            
            if request.channel not in config_classes:
                return {
                    "success": False,
                    "message": f"不支持的渠道: {request.channel}"
                }
            
            # 创建临时配置对象
            temp_config = config_classes[request.channel](**request.config)
            
            # 创建临时渠道实例进行测试
            from backend.modules.channels.qq import QQChannel
            from backend.modules.channels.feishu import FeishuChannel
            from backend.modules.channels.dingtalk import DingTalkChannel
            from backend.modules.channels.telegram import TelegramChannel
            
            channel_classes = {
                "qq": QQChannel,
                "feishu": FeishuChannel,
                "dingtalk": DingTalkChannel,
                "telegram": TelegramChannel,
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
        
        # 翻译 note 字段
        if result.get("bot_info") and result["bot_info"].get("note"):
            note = result["bot_info"]["note"]
            note_translations = {
                "Full connection test will be performed when channel is enabled": "启用渠道后将进行完整连接测试",
                "Format check passed. Real connection test will be performed when channel is enabled.": "格式检查通过。启用渠道后将进行真实连接测试。",
                "Successfully obtained access token from Feishu API": "成功从飞书 API 获取访问令牌",
                "Successfully authenticated with QQ API": "成功通过 QQ API 认证"
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
async def update_channel_config(request: ChannelConfigUpdate):
    """更新渠道配置"""
    try:
        config = config_loader.config
        
        # 支持的渠道列表
        supported_channels = ["telegram", "discord", "qq", "wechat", "dingtalk", "feishu"]
        
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
        supported_channels = ["telegram", "discord", "qq", "wechat", "dingtalk", "feishu"]
        
        if channel not in supported_channels:
            raise HTTPException(status_code=404, detail=f"Channel not found: {channel}")
        
        # 获取渠道配置
        channel_config = getattr(config.channels, channel, None)
        
        if not channel_config:
            # 如果配置不存在，创建默认配置
            logger.warning(f"Channel configuration not found for {channel}, creating default")
            from backend.modules.config.schema import (
                TelegramConfig, DiscordConfig, QQConfig, 
                WeChatConfig, DingTalkConfig, FeishuConfig
            )
            
            config_classes = {
                "telegram": TelegramConfig,
                "discord": DiscordConfig,
                "qq": QQConfig,
                "wechat": WeChatConfig,
                "dingtalk": DingTalkConfig,
                "feishu": FeishuConfig
            }
            
            channel_config = config_classes[channel]()
            setattr(config.channels, channel, channel_config)
            await config_loader.save()
        
        # 构建配置响应（根据不同渠道返回不同字段）
        config_dict = {
            "enabled": channel_config.enabled,
            "allow_from": getattr(channel_config, "allow_from", [])
        }
        
        # 添加渠道特定的配置字段
        if channel == "telegram":
            config_dict.update({
                "token": channel_config.token,
                "proxy": getattr(channel_config, "proxy", None)
            })
        elif channel == "discord":
            config_dict.update({
                "token": channel_config.token
            })
        elif channel == "qq":
            config_dict.update({
                "app_id": channel_config.app_id,
                "secret": channel_config.secret
            })
        elif channel == "wechat":
            config_dict.update({
                "app_id": channel_config.app_id,
                "app_secret": channel_config.app_secret
            })
        elif channel == "dingtalk":
            config_dict.update({
                "client_id": channel_config.client_id,
                "client_secret": channel_config.client_secret
            })
        elif channel == "feishu":
            config_dict.update({
                "app_id": channel_config.app_id,
                "app_secret": channel_config.app_secret,
                "encrypt_key": getattr(channel_config, "encrypt_key", ""),
                "verification_token": getattr(channel_config, "verification_token", "")
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
