"""频道管理器模块

负责频道的初始化、生命周期管理和消息路由。
所有频道在独立的监督任务中运行，异常退出后自动重连（指数退避）。
"""

import asyncio
from typing import Any

from loguru import logger

from backend.modules.channels.base import BaseChannel, InboundMessage, OutboundMessage
from backend.modules.messaging.enterprise_queue import EnterpriseMessageQueue

# 频道注册表：name -> (module_path, class_name)
_CHANNEL_REGISTRY: dict[str, tuple[str, str]] = {
    "telegram": ("backend.modules.channels.telegram", "TelegramChannel"),
    "discord": ("backend.modules.channels.discord", "DiscordChannel"),
    "qq": ("backend.modules.channels.qq", "QQChannel"),
    "wechat": ("backend.modules.channels.wechat", "WeChatChannel"),
    "dingtalk": ("backend.modules.channels.dingtalk", "DingTalkChannel"),
    "feishu": ("backend.modules.channels.feishu", "FeishuChannel"),
}


class ChannelManager:
    """频道管理器

    职责：
    - 根据配置初始化已启用的频道
    - 统一启动 / 停止所有频道
    - 将出站消息路由到对应频道
    - 监督频道运行状态，异常退出时自动重连
    """

    def __init__(self, config: Any, bus: EnterpriseMessageQueue):
        self.config = config
        self.bus = bus
        self.channels: dict[str, BaseChannel] = {}
        self._running = False
        self._init_channels()

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def _init_channels(self) -> None:
        """根据配置初始化已启用的频道。"""
        channels_config = getattr(self.config, "channels", None)
        if not channels_config:
            logger.info("No channels configuration found")
            return

        for name, (module_path, class_name) in _CHANNEL_REGISTRY.items():
            channel_cfg = getattr(channels_config, name, None)
            if not channel_cfg or not getattr(channel_cfg, "enabled", False):
                continue
            try:
                module = __import__(module_path, fromlist=[class_name])
                cls = getattr(module, class_name)
                self.channels[name] = cls(channel_cfg)
                logger.debug(f"{class_name} initialized")
            except ImportError as e:
                logger.warning(f"{name} channel not available: {e}")
            except Exception as e:
                logger.error(f"Failed to initialize {name} channel: {e}")

        logger.info(f"Initialized {len(self.channels)} channel(s): {list(self.channels.keys())}")

        for channel in self.channels.values():
            channel.set_message_callback(self._on_inbound_message)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start_all(self) -> None:
        """启动所有频道和出站消息调度器。"""
        if not self.channels:
            logger.warning("No channels to start")
            return

        self._running = True
        tasks = [asyncio.create_task(self._dispatch_outbound())]
        for name, channel in self.channels.items():
            tasks.append(asyncio.create_task(self._start_channel_supervised(name, channel)))
        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_all(self) -> None:
        """停止所有频道。"""
        logger.info("Stopping all channels...")
        self._running = False
        for name, channel in self.channels.items():
            try:
                await channel.stop()
                logger.info(f"Stopped {name} channel")
            except Exception as e:
                logger.error(f"Error stopping {name}: {e}")

    # ------------------------------------------------------------------
    # 频道监督
    # ------------------------------------------------------------------

    async def _start_channel_supervised(self, name: str, channel: BaseChannel) -> None:
        """在监督循环中启动频道。

        频道异常退出后自动重连，使用指数退避（5s -> 10s -> ... -> 300s）。
        如果频道成功运行超过 60 秒后才断开，退避时间重置。
        """
        initial_backoff = 5
        max_backoff = 300
        backoff = initial_backoff

        while self._running:
            start_time = asyncio.get_event_loop().time()
            try:
                logger.info(f"Starting {name} channel...")
                await channel.start()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Channel {name} error: {e}")

            if not self._running:
                break

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > 60:
                backoff = initial_backoff

            logger.warning(f"Channel {name} exited, restarting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

    # ------------------------------------------------------------------
    # 消息路由
    # ------------------------------------------------------------------

    async def _on_inbound_message(self, msg: InboundMessage) -> None:
        """入站消息回调：转发到消息总线。"""
        logger.debug(f"Inbound from {msg.channel}: {msg.content[:50]}...")
        await self.bus.publish_inbound(msg)

    async def _dispatch_outbound(self) -> None:
        """出站消息调度：从总线消费消息并路由到对应频道。"""
        logger.debug("Outbound dispatcher started")
        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_outbound(), timeout=1.0)
                channel = self.channels.get(msg.channel)
                if channel:
                    try:
                        await channel.send(msg)
                        logger.debug(f"Sent via {msg.channel} to {msg.chat_id}")
                    except Exception as e:
                        logger.error(f"Failed to send via {msg.channel}: {e}")
                else:
                    logger.warning(f"Unknown channel: {msg.channel}")
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    async def send_message(self, msg: OutboundMessage) -> None:
        """发送消息到指定频道（通过消息总线）。"""
        await self.bus.publish_outbound(msg)

    def get_channel(self, name: str) -> BaseChannel | None:
        """按名称获取频道实例。"""
        return self.channels.get(name)

    async def test_channel(self, name: str) -> dict[str, Any]:
        """测试指定频道的连接。"""
        if name not in _CHANNEL_REGISTRY:
            return {"success": False, "message": f"Unknown channel: {name}"}

        # 已初始化的频道直接测试
        channel = self.channels.get(name)
        if channel:
            try:
                return await channel.test_connection()
            except Exception as e:
                logger.error(f"Error testing {name}: {e}")
                return {"success": False, "message": f"Test failed: {e}"}

        # 未初始化则临时创建实例测试
        try:
            module_path, class_name = _CHANNEL_REGISTRY[name]
            module = __import__(module_path, fromlist=[class_name])
            cls = getattr(module, class_name)

            channels_config = getattr(self.config, "channels", None)
            if not channels_config:
                return {"success": False, "message": "Channels configuration not found"}

            channel_cfg = getattr(channels_config, name, None)
            if not channel_cfg:
                return {"success": False, "message": f"Configuration for {name} not found"}

            return await cls(channel_cfg).test_connection()
        except ImportError as e:
            return {"success": False, "message": f"Channel module not available: {e}"}
        except Exception as e:
            logger.error(f"Error testing {name}: {e}")
            return {"success": False, "message": f"Test failed: {e}"}

    def get_status(self) -> dict[str, Any]:
        """获取所有频道的运行状态。"""
        return {
            name: {
                "enabled": True,
                "running": channel.is_running,
                "display_name": channel.display_name,
            }
            for name, channel in self.channels.items()
        }

    @property
    def enabled_channels(self) -> list[str]:
        return list(self.channels.keys())

    @property
    def is_running(self) -> bool:
        return self._running
