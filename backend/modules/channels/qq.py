"""QQ 频道模块

使用 qq-botpy SDK 通过 WebSocket 接收消息，支持私聊和群聊。
QQ 被动回复有 5 分钟窗口限制，超时后自动降级为主动消息。
"""

import asyncio
import time
from collections import OrderedDict
from typing import Any

from loguru import logger

from backend.modules.channels.base import BaseChannel, OutboundMessage

try:
    import botpy
    from botpy.message import C2CMessage, GroupMessage, Message

    QQ_AVAILABLE = True
except ImportError:
    QQ_AVAILABLE = False
    botpy = None
    C2CMessage = None
    GroupMessage = None
    Message = None

# QQ 被动回复窗口（秒）
_PASSIVE_REPLY_TTL = 290  # 5 分钟窗口，提前 10 秒过期


def _make_bot_class(channel: "QQChannel") -> type:
    """动态创建绑定到指定频道实例的 Bot 类。"""
    if not QQ_AVAILABLE:
        return None

    intents = botpy.Intents(direct_message=True, public_messages=True)

    class _Bot(botpy.Client):
        def __init__(self):
            super().__init__(intents=intents)

        async def on_ready(self):
            logger.info(f"QQ bot ready: {self.robot.name}")

        async def on_c2c_message_create(self, message: C2CMessage):
            await channel._on_message(message)

        async def on_direct_message_create(self, message):
            await channel._on_message(message)

        async def on_group_at_message_create(self, message: GroupMessage):
            await channel._on_message(message)

    return _Bot


class QQChannel(BaseChannel):
    """QQ 频道

    通过 qq-botpy SDK 的 WebSocket 连接收发消息。
    支持私聊（C2C）和群聊（Group @）两种模式。
    """

    name = "qq"

    def __init__(self, config: Any):
        super().__init__(config)
        self._markdown_enabled = getattr(config, "markdown_enabled", True)
        self._group_markdown_enabled = getattr(config, "group_markdown_enabled", True)
        self._client = None
        self._processed_ids: OrderedDict[str, None] = OrderedDict()
        self._bot_task: asyncio.Task | None = None
        # 被动回复上下文缓存：chat_id -> {msg_id, event_id, is_group, timestamp}
        self._reply_context: OrderedDict[str, dict] = OrderedDict()
        self._msg_seq = 1

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """启动 QQ 机器人。"""
        if not QQ_AVAILABLE:
            logger.error("QQ SDK not installed. Run: pip install qq-botpy")
            return

        if not self.config.app_id or not self.config.secret:
            logger.error("QQ app_id and secret not configured")
            return

        self._running = True

        bot_cls = _make_bot_class(self)
        if not bot_cls:
            logger.error("Failed to create QQ bot class")
            return

        self._client = bot_cls()
        self._bot_task = asyncio.create_task(self._run_bot())
        logger.info("QQ bot started (private + group)")

    async def _run_bot(self) -> None:
        """运行 Bot 连接，断开后直接退出，由 manager 监督负责重连。"""
        try:
            await self._client.start(
                appid=self.config.app_id, secret=self.config.secret
            )
        except Exception as e:
            logger.warning(f"QQ bot connection exited: {e}")

    async def stop(self) -> None:
        """停止 QQ 机器人。"""
        self._running = False
        if self._bot_task:
            self._bot_task.cancel()
            try:
                await self._bot_task
            except asyncio.CancelledError:
                pass
        logger.info("QQ bot stopped")

    # ------------------------------------------------------------------
    # 入站消息处理
    # ------------------------------------------------------------------

    async def _on_message(self, data: Any) -> None:
        """处理 SDK 回调的入站消息。"""
        try:
            message_id = data.id

            # 消息去重
            if message_id in self._processed_ids:
                return
            self._processed_ids[message_id] = None
            if len(self._processed_ids) > 1000:
                self._processed_ids.popitem(last=False)

            author = data.author
            user_id = str(
                getattr(author, "id", None)
                or getattr(author, "user_openid", None)
                or getattr(author, "member_openid", "unknown")
            )

            content = (data.content or "").strip()
            if not content:
                return

            is_group = isinstance(data, GroupMessage) if GroupMessage else False
            chat_id = str(getattr(data, "group_openid", user_id)) if is_group else user_id

            logger.info(
                f"QQ {'group' if is_group else 'private'}: "
                f"{user_id}{' in ' + chat_id if is_group else ''}: {content[:50]}..."
            )

            # 缓存被动回复上下文（仅保留必要的轻量数据）
            self._reply_context[chat_id] = {
                "msg_id": getattr(data, "id", None),
                "event_id": getattr(data, "event_id", None),
                "is_group": is_group,
                "timestamp": time.time(),
            }
            if len(self._reply_context) > 200:
                self._reply_context.popitem(last=False)

            await self._handle_message(
                sender_id=user_id,
                chat_id=chat_id,
                content=content,
                metadata={"message_id": message_id, "is_group": is_group},
            )

        except Exception as e:
            logger.error(f"Error handling QQ message: {e}")
            logger.exception("Details:")

    # ------------------------------------------------------------------
    # 出站消息发送
    # ------------------------------------------------------------------

    async def send(self, msg: OutboundMessage) -> None:
        """发送消息到 QQ。"""
        if not self._client:
            logger.warning("QQ client not initialized")
            return

        try:
            is_group = (msg.metadata or {}).get("is_group", False)
            has_media = bool(msg.media)

            # 尝试获取被动回复上下文
            ctx = self._get_reply_context(msg.chat_id)
            if ctx:
                is_group = ctx["is_group"]

            if has_media:
                await self._send_media_message(
                    is_group=is_group,
                    chat_id=msg.chat_id,
                    content=msg.content,
                    media_files=msg.media,
                    msg_id=ctx["msg_id"] if ctx else None,
                )
            elif ctx:
                await self._send_passive_reply(msg, is_group, ctx)
            else:
                await self._send_active_message(msg, is_group)

        except Exception as e:
            logger.error(f"Error sending QQ message to {msg.chat_id}: {e}")
            self._log_error_hint(str(e))

    def _get_reply_context(self, chat_id: str) -> dict | None:
        """获取有效的被动回复上下文，过期则清除。"""
        ctx = self._reply_context.get(chat_id)
        if not ctx:
            return None

        if time.time() - ctx["timestamp"] > _PASSIVE_REPLY_TTL:
            del self._reply_context[chat_id]
            return None

        return ctx

    async def _send_passive_reply(
        self, msg: OutboundMessage, is_group: bool, ctx: dict
    ) -> None:
        """发送被动回复（在 5 分钟窗口内）。"""
        msg_id = ctx["msg_id"]
        event_id = ctx["event_id"]

        if is_group:
            use_md = self._group_markdown_enabled and self._markdown_enabled
            await self._send_group_message(
                msg.chat_id, msg.content, msg_id, event_id, use_markdown=use_md
            )
        else:
            await self._send_private_message(
                msg.chat_id, msg.content, msg_id, event_id,
                use_markdown=self._markdown_enabled,
            )

    async def _send_active_message(self, msg: OutboundMessage, is_group: bool) -> None:
        """发送主动消息（无被动回复上下文时）。"""
        if is_group:
            use_md = self._group_markdown_enabled and self._markdown_enabled
            await self._send_group_message(msg.chat_id, msg.content, use_markdown=use_md)
        else:
            self._msg_seq += 1
            await self._send_private_wakeup(msg.chat_id, msg.content, self._msg_seq)

    # ------------------------------------------------------------------
    # 底层发送方法
    # ------------------------------------------------------------------

    async def _send_group_message(
        self,
        chat_id: str,
        content: str,
        msg_id: str | None = None,
        event_id: str | None = None,
        use_markdown: bool = False,
    ) -> None:
        """发送群聊消息，markdown 失败自动降级为纯文本。"""
        params = {
            "group_openid": chat_id,
            "msg_type": 2 if use_markdown else 0,
            "content": None if use_markdown else content,
            "markdown": {"content": content} if use_markdown else None,
        }
        if msg_id:
            params["msg_id"] = msg_id
            params["msg_seq"] = 1
        if event_id:
            params["event_id"] = event_id
        params = {k: v for k, v in params.items() if v is not None}

        try:
            await self._client.api.post_group_message(**params)
        except Exception as e:
            if use_markdown and ("11255" in str(e) or "invalid request" in str(e)):
                logger.warning(f"Markdown not supported, fallback to plain text: {e}")
                params["msg_type"] = 0
                params["content"] = content
                params.pop("markdown", None)
                await self._client.api.post_group_message(**params)
            else:
                raise

    async def _send_private_message(
        self,
        chat_id: str,
        content: str,
        msg_id: str | None = None,
        event_id: str | None = None,
        msg_seq: int | None = None,
        use_markdown: bool = False,
    ) -> None:
        """发送私聊消息，markdown 失败自动降级为纯文本。"""
        params = {
            "openid": chat_id,
            "msg_type": 2 if use_markdown else 0,
            "content": None if use_markdown else content,
            "markdown": {"content": content} if use_markdown else None,
        }
        if msg_id:
            params["msg_id"] = msg_id
            params["msg_seq"] = msg_seq or 1
        if event_id:
            params["event_id"] = event_id
        params = {k: v for k, v in params.items() if v is not None}

        try:
            await self._client.api.post_c2c_message(**params)
        except Exception as e:
            if use_markdown and ("11255" in str(e) or "invalid request" in str(e)):
                logger.warning(f"Markdown not supported, fallback to plain text: {e}")
                params["msg_type"] = 0
                params["content"] = content
                params.pop("markdown", None)
                await self._client.api.post_c2c_message(**params)
            else:
                raise

    async def _send_private_wakeup(
        self, chat_id: str, content: str, msg_seq: int
    ) -> None:
        """发送私聊主动消息（互动召回）。"""
        try:
            if self._markdown_enabled:
                await self._send_private_message(
                    chat_id, content, msg_seq=msg_seq, use_markdown=True
                )
            else:
                params = {
                    "openid": chat_id,
                    "msg_type": 0,
                    "content": content,
                    "msg_seq": msg_seq,
                    "is_wakeup": True,
                }
                await self._client.api.post_c2c_message(**params)
        except TypeError as e:
            if "is_wakeup" in str(e):
                logger.debug("SDK does not support is_wakeup, using normal send")
                await self._send_private_message(
                    chat_id, content, msg_seq=msg_seq,
                    use_markdown=self._markdown_enabled,
                )
            else:
                raise

    async def _send_media_message(
        self,
        is_group: bool,
        chat_id: str,
        content: str,
        media_files: list[str],
        msg_id: str | None = None,
    ) -> None:
        """发送富媒体消息（图片/文件 URL）。"""
        for media_path in media_files:
            try:
                if not media_path.startswith(("http://", "https://")):
                    logger.warning(f"Non-URL media path ignored: {media_path}")
                    continue

                ext = media_path.lower().rsplit(".", 1)[-1] if "." in media_path else ""
                file_type = 1 if ext in ("jpg", "jpeg", "png", "gif", "bmp", "webp") else 2

                if is_group:
                    await self._client.api.post_group_file(
                        group_openid=chat_id, file_type=file_type,
                        url=media_path, srv_send_msg=True,
                    )
                else:
                    await self._client.api.post_c2c_file(
                        openid=chat_id, file_type=file_type,
                        url=media_path, srv_send_msg=True,
                    )

                # 媒体后追加文本说明
                if content:
                    await asyncio.sleep(0.5)
                    if is_group:
                        await self._send_group_message(chat_id, content)
                    else:
                        self._msg_seq += 1
                        await self._send_private_message(
                            chat_id, content, msg_seq=self._msg_seq
                        )

            except Exception as e:
                logger.error(f"Failed to send media {media_path}: {e}")

    # ------------------------------------------------------------------
    # 错误提示
    # ------------------------------------------------------------------

    @staticmethod
    def _log_error_hint(error_msg: str) -> None:
        """根据 QQ API 错误码输出友好提示。"""
        hints = {
            "40054005": "Message dedup: QQ has strict limits on private messages",
            "11255": "Private chat only supports passive reply within 5 min window",
            "22009": "Rate limit: 4 active msgs/month, 5 passive msgs/5min",
            "304082": "Rich media fetch failed, check file path and format",
            "304083": "Rich media fetch failed, check file path and format",
        }
        for code, hint in hints.items():
            if code in error_msg:
                logger.warning(hint)
                return

    # ------------------------------------------------------------------
    # 连接测试
    # ------------------------------------------------------------------

    async def test_connection(self) -> dict[str, Any]:
        """测试 QQ 连接（验证凭据）。"""
        if not self.config.app_id or not self.config.secret:
            return {"success": False, "message": "App ID or Secret not configured"}

        if not QQ_AVAILABLE:
            return {"success": False, "message": "QQ SDK not installed"}

        try:
            if len(self.config.app_id) < 8 or not self.config.app_id.isdigit():
                return {"success": False, "message": "Invalid App ID format (should be numeric, 8+ digits)"}
            if len(self.config.secret) < 16 or not all(c.isalnum() for c in self.config.secret):
                return {"success": False, "message": "Invalid Secret format (should be alphanumeric, 16+ chars)"}

            intents = botpy.Intents(direct_message=True, public_messages=True)

            class _TestBot(botpy.Client):
                def __init__(self):
                    super().__init__(intents=intents)
                    self.auth_success = False

                async def on_ready(self):
                    self.auth_success = True
                    await self.close()

            test_bot = _TestBot()
            try:
                task = asyncio.create_task(
                    test_bot.start(appid=self.config.app_id, secret=self.config.secret)
                )
                await asyncio.wait_for(task, timeout=5.0)
                return {
                    "success": True,
                    "message": "QQ credentials verified",
                    "bot_info": {"app_id": self.config.app_id[:8] + "...", "status": "verified"},
                }
            except asyncio.TimeoutError:
                if test_bot.auth_success:
                    return {"success": True, "message": "QQ credentials verified"}
                return {"success": False, "message": "Connection timeout"}
            except Exception as e:
                err = str(e).lower()
                if "401" in err or "unauthorized" in err:
                    return {"success": False, "message": "Invalid credentials"}
                if "403" in err:
                    return {"success": False, "message": "Access denied"}
                return {"success": False, "message": f"Auth failed: {e}"}
            finally:
                try:
                    if hasattr(test_bot, "close"):
                        await test_bot.close()
                except Exception:
                    pass

        except Exception as e:
            return {"success": False, "message": f"Test failed: {e}"}

    @property
    def display_name(self) -> str:
        return "QQ"
