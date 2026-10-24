"""频道基类模块

定义所有聊天频道的抽象接口和消息数据结构。
每个具体频道（Telegram、飞书、钉钉等）都应继承 BaseChannel 并实现其抽象方法。
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.modules.channels.media_utils import (
    DEFAULT_INBOUND_ATTACHMENT_PROMPT,
    MAX_INBOUND_ATTACHMENTS,
)


@dataclass
class InboundMessage:
    """入站消息 - 从聊天平台接收"""

    channel: str
    sender_id: str
    chat_id: str
    content: str
    media: List[str] = None
    metadata: Dict[str, Any] = None

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
    media: Optional[List[str]] = None
    metadata: Dict[str, Any] = None

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

    # 长连接运行时状态，供管理器和前端统一读取。
    RUNTIME_STOPPED = "stopped"
    RUNTIME_STARTING = "starting"
    RUNTIME_CONNECTING = "connecting"
    RUNTIME_RUNNING = "running"
    RUNTIME_STOPPING = "stopping"
    RUNTIME_FAILED = "failed"

    def __init__(self, config: Any):
        self.config = config
        self._running = False
        self._message_callback = None
        self._account_id = str(getattr(config, "account_id", "default") or "default")
        self._instance_key = f"{self.name}:{self._account_id}"
        self._runtime_state = self.RUNTIME_STOPPED
        self._runtime_error = ""
        self._runtime_updated_at = time.time()
        self._runtime_reconnect_attempts = 0

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
    async def test_connection(self) -> Dict[str, Any]:
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
        raw_allow_list = getattr(self.config, "allow_from", [])
        allow_list = [
            str(item).strip()
            for item in (raw_allow_list or [])
            if str(item).strip()
        ]
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
        media: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """处理入站消息：校验权限后转发到回调。"""
        if not self.is_allowed(sender_id):
            logger.warning(
                f"Access denied for {sender_id} on {self.name}, "
                f"add to allow_from to grant access"
            )
            return

        normalized_media = list(media or [])
        dropped_media_count = 0
        if len(normalized_media) > MAX_INBOUND_ATTACHMENTS:
            dropped_media_count = len(normalized_media) - MAX_INBOUND_ATTACHMENTS
            normalized_media = normalized_media[:MAX_INBOUND_ATTACHMENTS]

        normalized_content = str(content or "").strip()
        # 只发附件不带文字时，给 Agent 一个明确的默认指令。
        if not normalized_content and normalized_media:
            normalized_content = DEFAULT_INBOUND_ATTACHMENT_PROMPT
        if dropped_media_count:
            normalized_content = (
                f"{normalized_content}\n\n"
                f"（附件数量超过上限，已仅保留前 {MAX_INBOUND_ATTACHMENTS} 个，"
                f"忽略 {dropped_media_count} 个）"
            )

        msg = InboundMessage(
            channel=self.name,
            sender_id=str(sender_id),
            chat_id=str(chat_id),
            content=normalized_content,
            media=normalized_media,
            metadata={
                **(metadata or {}),
                "account_id": str((metadata or {}).get("account_id") or self._account_id),
                "instance_key": str((metadata or {}).get("instance_key") or self._instance_key),
            },
        )

        if self._message_callback:
            await self._message_callback(msg)
        else:
            logger.warning(f"No message callback set for channel {self.name}")

    # ------------------------------------------------------------------
    # 运行时状态
    # ------------------------------------------------------------------

    def set_runtime_state(
        self,
        state: str,
        *,
        error: str = "",
        reconnect_attempts: Optional[int] = None,
    ) -> None:
        """更新渠道运行时状态；任何渠道实现都通过这一个入口写入。"""
        normalized = str(state or "").strip() or self.RUNTIME_STOPPED
        changed = normalized != self._runtime_state or error != self._runtime_error
        self._runtime_state = normalized
        self._runtime_error = str(error or "")
        self._runtime_updated_at = time.time()
        if reconnect_attempts is not None:
            self._runtime_reconnect_attempts = max(0, int(reconnect_attempts))
        if changed:
            if normalized == self.RUNTIME_FAILED:
                logger.warning(
                    f"[{self._instance_key}] runtime state -> {normalized}: {self._runtime_error}"
                )
            else:
                logger.info(
                    f"[{self._instance_key}] runtime state -> {normalized}"
                    + (f" ({self._runtime_error})" if self._runtime_error else "")
                )

    async def notify_queued(self, msg: "InboundMessage", position: int = 0) -> None:
        """可选能力：会话忙碌时告知用户消息已排队。默认不发送。"""
        return None

    def get_runtime_status(self) -> Dict[str, Any]:
        """返回统一的运行时状态快照。"""
        return {
            "state": self._runtime_state,
            "healthy_running": bool(
                self._running and self._runtime_state == self.RUNTIME_RUNNING
            ),
            "running": bool(self._running),
            "last_error": self._runtime_error,
            "updated_at": self._runtime_updated_at,
            "reconnect_attempts": self._runtime_reconnect_attempts,
        }

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def display_name(self) -> str:
        configured_name = str(getattr(self.config, "display_name", "") or "").strip()
        if configured_name:
            return configured_name
        if self._account_id == "default":
            return self.name.capitalize()
        return f"{self.name.capitalize()} [{self._account_id}]"

    @property
    def account_id(self) -> str:
        return self._account_id

    @property
    def instance_key(self) -> str:
        return self._instance_key
