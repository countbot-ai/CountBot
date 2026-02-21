"""频道基类模块

定义所有聊天频道的抽象接口和消息数据结构。
每个具体频道（Telegram、飞书、钉钉等）都应继承 BaseChannel 并实现其抽象方法。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from loguru import logger


@dataclass
class InboundMessage:
    """入站消息 - 从聊天平台接收"""

    channel: str
    sender_id: str
    chat_id: str
    content: str
    media: list[str] = None
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.media is None:
            self.media = []
        if self.metadata is None:
            self.metadata = {}


@dataclass
class OutboundMessage:
    """出站消息 - 发送到聊天平台"""

    channel: str
    chat_id: str
    content: str
    media: list[str] | None = None
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.media is None:
            self.media = []
        if self.metadata is None:
            self.metadata = {}


class BaseChannel(ABC):
    """频道抽象基类

    所有聊天频道的公共接口，提供：
    - 生命周期管理（start / stop）
    - 消息收发（send / _handle_message）
    - 权限校验（is_allowed）
    - 连接测试（test_connection）
    """

    name: str = "base"

    def __init__(self, config: Any):
        self.config = config
        self._running = False
        self._message_callback = None

    # ------------------------------------------------------------------
    # 抽象方法 - 子类必须实现
    # ------------------------------------------------------------------

    @abstractmethod
    async def start(self) -> None:
        """启动频道，开始监听消息。"""

    @abstractmethod
    async def stop(self) -> None:
        """停止频道，释放资源。"""

    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        """通过此频道发送消息。"""

    @abstractmethod
    async def test_connection(self) -> dict[str, Any]:
        """测试频道连接，返回 ``{success: bool, message: str}``。"""

    # ------------------------------------------------------------------
    # 消息回调
    # ------------------------------------------------------------------

    def set_message_callback(self, callback) -> None:
        """设置入站消息回调（由 ChannelManager 调用）。"""
        self._message_callback = callback

    # ------------------------------------------------------------------
    # 权限校验
    # ------------------------------------------------------------------

    def is_allowed(self, sender_id: str) -> bool:
        """检查发送者是否在白名单中。空白名单表示允许所有人。"""
        allow_list = getattr(self.config, "allow_from", [])
        if not allow_list:
            return True

        sender_str = str(sender_id)
        if sender_str in allow_list:
            return True

        # 支持 "id|username" 复合格式
        if "|" in sender_str:
            for part in sender_str.split("|"):
                if part and part in allow_list:
                    return True

        return False

    # ------------------------------------------------------------------
    # 入站消息处理
    # ------------------------------------------------------------------

    async def _handle_message(
        self,
        sender_id: str,
        chat_id: str,
        content: str,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """处理入站消息：校验权限后转发到回调。"""
        if not self.is_allowed(sender_id):
            logger.warning(
                f"Access denied for {sender_id} on {self.name}, "
                f"add to allow_from to grant access"
            )
            return

        msg = InboundMessage(
            channel=self.name,
            sender_id=str(sender_id),
            chat_id=str(chat_id),
            content=content,
            media=media or [],
            metadata=metadata or {},
        )

        if self._message_callback:
            await self._message_callback(msg)
        else:
            logger.warning(f"No message callback set for channel {self.name}")

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def display_name(self) -> str:
        return self.name.capitalize()
