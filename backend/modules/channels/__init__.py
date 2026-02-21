"""多渠道支持模块 - 提供统一的消息总线架构"""

from backend.modules.channels.base import BaseChannel
from backend.modules.channels.manager import ChannelManager

__all__ = ["BaseChannel", "ChannelManager"]
