"""频道管理器模块

负责频道的初始化、生命周期管理和消息路由。
所有频道在独立的监督任务中运行，异常退出后自动重连（指数退避）。
"""

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from backend.modules.channels.base import BaseChannel, InboundMessage, OutboundMessage
from backend.modules.messaging.enterprise_queue import EnterpriseMessageQueue

# 频道注册表：name -> (module_path, class_name)
_CHANNEL_REGISTRY: Dict[str, Tuple[str, str]] = {
    "telegram": ("backend.modules.channels.telegram", "TelegramChannel"),
    "qq": ("backend.modules.channels.qq", "QQChannel"),
    "dingtalk": ("backend.modules.channels.dingtalk", "DingTalkChannel"),
    "feishu": ("backend.modules.channels.feishu", "FeishuChannel"),
    "weibo": ("backend.modules.channels.weibo", "WeiboChannel"),
    "wecom": ("backend.modules.channels.wecom", "WeComChannel"),
    "xiaozhi": ("backend.modules.channels.xiaozhi", "XiaozhiChannel"),
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
        self.channels: Dict[str, BaseChannel] = {}
        self._channels_by_type: Dict[str, List[str]] = {}
        self._default_channel_keys: Dict[str, str] = {}
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
            if not channel_cfg:
                continue
            try:
                module = __import__(module_path, fromlist=[class_name])
                cls = getattr(module, class_name)
                instances = self._iter_channel_instances(name, channel_cfg)
                if not instances:
                    continue
                for instance_key, instance_cfg, account_id in instances:
                    channel = cls(instance_cfg)
                    self.channels[instance_key] = channel
                    self._channels_by_type.setdefault(name, []).append(instance_key)
                    if name not in self._default_channel_keys:
                        self._default_channel_keys[name] = instance_key
                    setattr(channel, "_instance_key", instance_key)
                    setattr(channel, "_account_id", account_id)
                    logger.debug(f"{class_name} initialized for {instance_key}")
            except ImportError as e:
                logger.warning(f"{name} channel not available: {e}")
            except Exception as e:
                logger.error(f"Failed to initialize {name} channel: {e}")

        logger.info(f"Initialized {len(self.channels)} channel(s): {list(self.channels.keys())}")

        for channel in self.channels.values():
            channel.set_message_callback(self._on_inbound_message)

    @staticmethod
    def _build_instance_key(channel_name: str, account_id: str) -> str:
        return f"{channel_name}:{account_id}"

    def _iter_channel_instances(self, channel_name: str, channel_cfg: Any) -> List[Tuple[str, Any, str]]:
        """展开单渠道配置为多个机器人实例配置。"""
        instances: List[Tuple[str, Any, str]] = []
        seen_keys: set[str] = set()
        seen_signatures: Dict[str, str] = {}
        base_config_data = channel_cfg.model_dump(exclude={"accounts"})

        unique_field_map = {
            "telegram": ("token",),
            "qq": ("app_id",),
            "dingtalk": ("client_id",),
            "feishu": ("app_id",),
            "weibo": ("app_id",),
            "wecom": ("bot_id",),
        }

        def build_signature(config_data: Dict[str, Any]) -> Optional[str]:
            fields = unique_field_map.get(channel_name)
            if not fields:
                return None
            parts = []
            for field in fields:
                value = str(config_data.get(field) or "").strip()
                if not value:
                    return None
                parts.append(f"{field}={value}")
            return "|".join(parts)

        def register_signature(account_id: str, config_data: Dict[str, Any]) -> bool:
            signature = build_signature(config_data)
            if not signature:
                return True
            existing = seen_signatures.get(signature)
            if existing is not None:
                logger.warning(
                    f"Duplicate physical bot detected for {channel_name}: "
                    f"account '{account_id}' reuses credentials from '{existing}' ({signature})"
                )
                return False
            seen_signatures[signature] = account_id
            return True

        top_level_enabled = bool(getattr(channel_cfg, "enabled", False))
        top_level_account_id = str(getattr(channel_cfg, "account_id", "default") or "default")
        if top_level_enabled:
            if not register_signature(top_level_account_id, base_config_data):
                logger.warning(
                    f"Skipping duplicated channel account: {self._build_instance_key(channel_name, top_level_account_id)}"
                )
            else:
                top_level_cfg = channel_cfg.model_copy(update={"account_id": top_level_account_id})
                top_level_key = self._build_instance_key(channel_name, top_level_account_id)
                instances.append(
                    (
                        top_level_key,
                        top_level_cfg,
                        top_level_account_id,
                    )
                )
                seen_keys.add(top_level_key)

        accounts = getattr(channel_cfg, "accounts", {}) or {}
        for raw_account_id, account_cfg in accounts.items():
            account_id = str(raw_account_id or getattr(account_cfg, "account_id", "default") or "default")
            if isinstance(account_cfg, dict):
                enabled = bool(account_cfg.get("enabled", False))
            else:
                enabled = bool(getattr(account_cfg, "enabled", False))
            if not enabled:
                continue
            instance_key = self._build_instance_key(channel_name, account_id)
            if instance_key in seen_keys:
                logger.warning(f"Duplicate channel account ignored: {instance_key}")
                continue
            if isinstance(account_cfg, dict):
                merged_data = {
                    **base_config_data,
                    **account_cfg,
                    "account_id": account_id,
                    "accounts": {},
                }
                if not register_signature(account_id, merged_data):
                    logger.warning(f"Skipping duplicated channel account: {instance_key}")
                    continue
                instance_cfg = channel_cfg.__class__(**merged_data)
            else:
                if not register_signature(account_id, account_cfg.model_dump()):
                    logger.warning(f"Skipping duplicated channel account: {instance_key}")
                    continue
                instance_cfg = account_cfg.model_copy(update={"account_id": account_id})
            instances.append(
                (
                    instance_key,
                    instance_cfg,
                    account_id,
                )
            )
            seen_keys.add(instance_key)
        return instances

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
                if self._running and channel.is_running:
                    logger.info(f"Channel {name} is running in background mode")
                    while self._running and channel.is_running:
                        await asyncio.sleep(1)
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
                channel = self._resolve_outbound_channel(msg)
                if channel:
                    try:
                        await channel.send(msg)
                        logger.debug(
                            f"Sent via {getattr(channel, 'instance_key', msg.channel)} to {msg.chat_id}"
                        )
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

    def _resolve_outbound_channel(self, msg: OutboundMessage) -> Optional[BaseChannel]:
        """根据 channel + account_id 解析具体机器人实例。"""
        metadata = msg.metadata or {}
        account_id = str(metadata.get("account_id") or "").strip()
        if account_id:
            instance_key = self._build_instance_key(msg.channel, account_id)
            channel = self.channels.get(instance_key)
            if channel:
                return channel
            logger.warning(f"Channel instance not found: {instance_key}, fallback to default")

        default_key = self._default_channel_keys.get(msg.channel)
        if default_key:
            return self.channels.get(default_key)
        return self.channels.get(msg.channel)

    def get_channel(self, name: str, account_id: Optional[str] = None) -> Optional[BaseChannel]:
        """按名称获取频道实例。"""
        if account_id:
            return self.channels.get(self._build_instance_key(name, account_id))
        default_key = self._default_channel_keys.get(name)
        if default_key:
            return self.channels.get(default_key)
        return self.channels.get(name)

    async def test_channel(self, name: str, account_id: Optional[str] = None) -> Dict[str, Any]:
        """测试指定频道的连接。"""
        if name not in _CHANNEL_REGISTRY:
            return {"success": False, "message": f"Unknown channel: {name}"}

        # 已初始化的频道直接测试
        channel = self.get_channel(name, account_id=account_id)
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

            temp_instances = self._iter_channel_instances(name, channel_cfg)
            temp_cfg = channel_cfg
            if temp_instances:
                if account_id:
                    matched = next(
                        (instance_cfg for _, instance_cfg, instance_account_id in temp_instances if instance_account_id == account_id),
                        None,
                    )
                    if matched is None:
                        return {
                            "success": False,
                            "message": f"Channel account not found: {name}:{account_id}",
                        }
                    temp_cfg = matched
                else:
                    _, temp_cfg, _ = temp_instances[0]
            return await cls(temp_cfg).test_connection()
        except ImportError as e:
            return {"success": False, "message": f"Channel module not available: {e}"}
        except Exception as e:
            logger.error(f"Error testing {name}: {e}")
            return {"success": False, "message": f"Test failed: {e}"}

    def get_status(self) -> Dict[str, Any]:
        """获取所有频道的运行状态。"""
        grouped: Dict[str, Any] = {}
        for channel_type, instance_keys in self._channels_by_type.items():
            instances = {}
            running = False
            for instance_key in instance_keys:
                channel = self.channels[instance_key]
                account_id = getattr(channel, "account_id", "default")
                instances[account_id] = {
                    "enabled": True,
                    "running": channel.is_running,
                    "display_name": channel.display_name,
                    "instance_key": instance_key,
                }
                running = running or channel.is_running

            grouped[channel_type] = {
                "enabled": bool(instances),
                "running": running,
                "display_name": channel_type.capitalize(),
                "instances": instances,
            }
        return grouped

    @property
    def enabled_channels(self) -> List[str]:
        return list(self.channels.keys())

    @property
    def is_running(self) -> bool:
        return self._running
