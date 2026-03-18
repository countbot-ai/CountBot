"""QQ 频道模块

使用 qq-botpy SDK 通过 WebSocket 接收消息，支持私聊和群聊。
QQ 被动回复有 5 分钟窗口限制，超时后自动降级为主动消息。
富媒体发送通过官方文件上传接口完成，支持本地文件与公网 URL。
"""

import asyncio
import base64
import hashlib
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from loguru import logger

from backend.modules.channels.base import BaseChannel, OutboundMessage
from backend.modules.channels.media_utils import download_to_temp, format_inbound_media_text

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
_QQ_TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
_QQ_API_BASE = "https://api.sgroup.qq.com"
_UPLOAD_CACHE_LIMIT = 500

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
_VOICE_EXTENSIONS = {".silk", ".wav", ".mp3", ".amr", ".ogg", ".m4a"}


class _QQMediaType:
    IMAGE = 1
    VIDEO = 2
    VOICE = 3
    FILE = 4


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
        self._http: Optional[httpx.AsyncClient] = None
        self._processed_ids: OrderedDict[str, None] = OrderedDict()
        self._bot_task: Optional[asyncio.Task] = None
        # 被动回复上下文缓存：chat_id -> {msg_id, event_id, is_group, timestamp}
        self._reply_context: OrderedDict[str, dict] = OrderedDict()
        self._msg_seq = 1
        self._reply_sequences: OrderedDict[str, int] = OrderedDict()
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0
        self._upload_cache: OrderedDict[str, dict] = OrderedDict()

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
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0))

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
        finally:
            self._running = False

    async def stop(self) -> None:
        """停止 QQ 机器人。"""
        self._running = False
        if self._bot_task:
            self._bot_task.cancel()
            try:
                await self._bot_task
            except asyncio.CancelledError:
                pass
        if self._http:
            await self._http.aclose()
            self._http = None
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
            sender_name = str(
                getattr(author, "username", None)
                or getattr(author, "nick", None)
                or getattr(author, "nickname", None)
                or user_id
            )

            content = (data.content or "").strip()
            media_files = await self._download_inbound_attachments(data)
            if media_files:
                content = format_inbound_media_text(media_files, content)
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
                media=media_files or None,
                metadata={
                    "message_id": message_id,
                    "is_group": is_group,
                    "sender_name": sender_name,
                },
            )

        except Exception as e:
            logger.error(f"Error handling QQ message: {e}")
            logger.exception("Details:")

    async def _download_inbound_attachments(self, data: Any) -> List[str]:
        """下载 QQ 入站附件到本地临时目录。"""
        if not self._http:
            return []

        media_files: List[str] = []
        attachments = getattr(data, "attachments", None) or []
        for attachment in attachments:
            try:
                url = getattr(attachment, "url", None)
                if not url:
                    continue
                if str(url).startswith("//"):
                    url = f"https:{url}"

                local_path = await download_to_temp(
                    self.name,
                    str(url),
                    client=self._http,
                    message_id=getattr(data, "id", None),
                    filename=getattr(attachment, "filename", None),
                    content_type=getattr(attachment, "content_type", None),
                    prefix="qq_attachment",
                )
                media_files.append(local_path)
            except Exception as e:
                logger.error(f"Failed to download QQ attachment: {e}")

        return media_files

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
                await self._send_with_media(msg, is_group, ctx)
            elif ctx:
                await self._send_passive_reply(msg, is_group, ctx)
            else:
                await self._send_active_message(msg, is_group)

        except Exception as e:
            logger.error(f"Error sending QQ message to {msg.chat_id}: {e}")
            self._log_error_hint(str(e))

    def _get_reply_context(self, chat_id: str) -> Optional[dict]:
        """获取有效的被动回复上下文，过期则清除。"""
        ctx = self._reply_context.get(chat_id)
        if not ctx:
            return None

        if time.time() - ctx["timestamp"] > _PASSIVE_REPLY_TTL:
            if ctx.get("msg_id"):
                self._reply_sequences.pop(ctx["msg_id"], None)
            del self._reply_context[chat_id]
            return None

        return ctx

    def _next_reply_seq(self, msg_id: str, requested: Optional[int] = None) -> int:
        """为同一条被动回复上下文分配递增 msg_seq，避免被 QQ 去重。"""
        last_seq = self._reply_sequences.get(msg_id, 0)
        seq = max(last_seq + 1, requested or 0) if requested is not None else last_seq + 1
        self._reply_sequences[msg_id] = seq
        self._reply_sequences.move_to_end(msg_id)
        while len(self._reply_sequences) > 500:
            self._reply_sequences.popitem(last=False)
        return seq

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
        use_md = (
            self._group_markdown_enabled and self._markdown_enabled
            if is_group
            else self._markdown_enabled
        )
        await self._send_proactive_message(msg.chat_id, msg.content, is_group, use_md)

    # ------------------------------------------------------------------
    # 底层发送方法
    # ------------------------------------------------------------------

    async def _send_group_message(
        self,
        chat_id: str,
        content: str,
        msg_id: Optional[str] = None,
        event_id: Optional[str] = None,
        msg_seq: Optional[int] = None,
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
            params["msg_seq"] = self._next_reply_seq(msg_id, msg_seq)
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
        msg_id: Optional[str] = None,
        event_id: Optional[str] = None,
        msg_seq: Optional[int] = None,
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
            params["msg_seq"] = self._next_reply_seq(msg_id, msg_seq)
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

    async def _send_proactive_message(
        self,
        chat_id: str,
        content: str,
        is_group: bool,
        use_markdown: bool,
    ) -> None:
        """通过官方 REST 接口发送主动消息。"""
        if not self._http:
            return

        access_token = await self._get_access_token()
        if not access_token:
            return

        body: Dict[str, Any] = (
            {"msg_type": 2, "markdown": {"content": content}}
            if use_markdown
            else {"msg_type": 0, "content": content}
        )
        endpoint = (
            f"/v2/groups/{chat_id}/messages"
            if is_group
            else f"/v2/users/{chat_id}/messages"
        )
        headers = {
            "Authorization": f"QQBot {access_token}",
            "Content-Type": "application/json",
        }

        try:
            resp = await self._http.post(
                f"{_QQ_API_BASE}{endpoint}",
                json=body,
                headers=headers,
            )
            resp.raise_for_status()
        except Exception as e:
            if use_markdown and ("11255" in str(e) or "invalid request" in str(e)):
                logger.warning(
                    f"QQ proactive markdown not supported, fallback to plain text: {e}"
                )
                await self._send_proactive_message(chat_id, content, is_group, False)
                return
            raise

    async def _send_with_media(
        self,
        msg: OutboundMessage,
        is_group: bool,
        ctx: Optional[dict],
    ) -> None:
        """发送带媒体文件的消息。"""
        seq = 0

        if msg.content and msg.content.strip():
            seq += 1
            if ctx:
                if is_group:
                    await self._send_group_message(
                        msg.chat_id,
                        msg.content,
                        ctx.get("msg_id"),
                        ctx.get("event_id"),
                        msg_seq=seq,
                        use_markdown=self._group_markdown_enabled and self._markdown_enabled,
                    )
                else:
                    await self._send_private_message(
                        msg.chat_id,
                        msg.content,
                        ctx.get("msg_id"),
                        ctx.get("event_id"),
                        msg_seq=seq,
                        use_markdown=self._markdown_enabled,
                    )
            else:
                await self._send_active_message(msg, is_group)

        for media_path in msg.media:
            if not media_path:
                continue
            seq += 1
            await self._send_media_file(msg.chat_id, media_path, is_group, ctx, seq)

    async def _send_media_file(
        self,
        chat_id: str,
        media_path: str,
        is_group: bool,
        ctx: Optional[dict],
        msg_seq: int,
    ) -> None:
        """根据文件类型发送图片、视频、语音或文件。"""
        media_kind = self._detect_media_kind(media_path)
        try:
            if media_kind == _QQMediaType.IMAGE:
                await self._send_rich_media(chat_id, media_path, is_group, ctx, msg_seq, _QQMediaType.IMAGE)
            elif media_kind == _QQMediaType.VIDEO:
                await self._send_rich_media(chat_id, media_path, is_group, ctx, msg_seq, _QQMediaType.VIDEO)
            elif media_kind == _QQMediaType.VOICE:
                await self._send_rich_media(chat_id, media_path, is_group, ctx, msg_seq, _QQMediaType.VOICE)
            else:
                await self._send_rich_media(chat_id, media_path, is_group, ctx, msg_seq, _QQMediaType.FILE)
        except Exception as e:
            logger.error(f"Failed to send media {media_path}: {e}")

    @staticmethod
    def _detect_media_kind(media_path: str) -> int:
        suffix = Path(media_path).suffix.lower()
        if suffix in _IMAGE_EXTENSIONS:
            return _QQMediaType.IMAGE
        if suffix in _VIDEO_EXTENSIONS:
            return _QQMediaType.VIDEO
        if suffix in _VOICE_EXTENSIONS:
            return _QQMediaType.VOICE
        return _QQMediaType.FILE

    @staticmethod
    def _is_remote_media(media_path: str) -> bool:
        return media_path.startswith(("http://", "https://"))

    @staticmethod
    def _build_upload_cache_key(file_bytes: bytes, scope: str, target_id: str, file_type: int) -> str:
        digest = hashlib.md5(file_bytes).hexdigest()
        return f"{digest}:{scope}:{target_id}:{file_type}"

    def _get_cached_file_info(self, cache_key: str) -> Optional[str]:
        cached = self._upload_cache.get(cache_key)
        if not cached:
            return None
        if time.time() >= cached["expires_at"]:
            self._upload_cache.pop(cache_key, None)
            return None
        return cached["file_info"]

    def _set_cached_file_info(self, cache_key: str, file_info: str, ttl: int) -> None:
        now = time.time()
        self._upload_cache = OrderedDict(
            (k, v) for k, v in self._upload_cache.items() if now < v["expires_at"]
        )
        if len(self._upload_cache) >= _UPLOAD_CACHE_LIMIT:
            while len(self._upload_cache) >= _UPLOAD_CACHE_LIMIT:
                self._upload_cache.popitem(last=False)
        effective_ttl = max(int(ttl) - 60, 10)
        self._upload_cache[cache_key] = {
            "file_info": file_info,
            "expires_at": now + effective_ttl,
        }

    def _next_msg_seq(self) -> int:
        self._msg_seq = (self._msg_seq % 65535) + 1
        return self._msg_seq

    async def _get_access_token(self) -> Optional[str]:
        """获取 QQ Bot access token。"""
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token
        if not self._http:
            return None

        try:
            resp = await self._http.post(
                _QQ_TOKEN_URL,
                json={
                    "appId": str(self.config.app_id).strip(),
                    "clientSecret": str(self.config.secret).strip(),
                },
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get("access_token")
            if not token:
                logger.error(f"Failed to get QQ access token: {data}")
                return None
            self._access_token = token
            self._token_expiry = time.time() + int(data.get("expires_in", 7200)) - 300
            return self._access_token
        except Exception as e:
            logger.error(f"Failed to get QQ access token: {e}")
            return None

    async def _upload_media(
        self,
        chat_id: str,
        media_path: str,
        is_group: bool,
        file_type: int,
    ) -> Optional[str]:
        """上传媒体到 QQ 官方接口，返回 file_info。"""
        if not self._http:
            return None

        access_token = await self._get_access_token()
        if not access_token:
            return None

        file_name: Optional[str] = None
        body: Dict[str, Any] = {
            "file_type": file_type,
            "srv_send_msg": False,
        }
        cache_key: Optional[str] = None

        if self._is_remote_media(media_path):
            body["url"] = media_path
            if file_type == _QQMediaType.FILE:
                file_name = Path(media_path.split("?", 1)[0]).name or "attachment"
        else:
            file = Path(media_path).expanduser()
            if not file.exists() or not file.is_file():
                logger.error(f"File not found: {media_path}")
                return None
            file_bytes = file.read_bytes()
            body["file_data"] = base64.b64encode(file_bytes).decode("utf-8")
            file_name = file.name
            cache_key = self._build_upload_cache_key(
                file_bytes,
                "group" if is_group else "c2c",
                chat_id,
                file_type,
            )
            cached_info = self._get_cached_file_info(cache_key)
            if cached_info:
                return cached_info

        if file_type == _QQMediaType.FILE and file_name:
            body["file_name"] = file_name

        endpoint = f"/v2/groups/{chat_id}/files" if is_group else f"/v2/users/{chat_id}/files"
        headers = {
            "Authorization": f"QQBot {access_token}",
            "Content-Type": "application/json",
        }

        try:
            resp = await self._http.post(
                f"{_QQ_API_BASE}{endpoint}",
                json=body,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            file_info = data.get("file_info")
            if not file_info:
                logger.error(f"QQ media upload missing file_info: {data}")
                return None

            ttl = data.get("ttl")
            if cache_key and ttl:
                self._set_cached_file_info(cache_key, file_info, int(ttl))
            return file_info
        except Exception as e:
            logger.error(f"Failed to upload QQ media {media_path}: {e}")
            return None

    async def _send_rich_media(
        self,
        chat_id: str,
        media_path: str,
        is_group: bool,
        ctx: Optional[dict],
        msg_seq: int,
        file_type: int,
    ) -> None:
        """发送上传后的 QQ 富媒体消息。"""
        if not self._http:
            return

        access_token = await self._get_access_token()
        if not access_token:
            return

        file_info = await self._upload_media(chat_id, media_path, is_group, file_type)
        if not file_info:
            return

        body: Dict[str, Any] = {
            "msg_type": 7,
            "media": {"file_info": file_info},
            "msg_seq": (
                self._next_reply_seq(ctx["msg_id"], msg_seq)
                if ctx and ctx.get("msg_id")
                else self._next_msg_seq()
            ),
        }
        if ctx and ctx.get("msg_id"):
            body["msg_id"] = ctx["msg_id"]
        if ctx and ctx.get("event_id"):
            body["event_id"] = ctx["event_id"]

        endpoint = f"/v2/groups/{chat_id}/messages" if is_group else f"/v2/users/{chat_id}/messages"
        headers = {
            "Authorization": f"QQBot {access_token}",
            "Content-Type": "application/json",
        }

        try:
            resp = await self._http.post(
                f"{_QQ_API_BASE}{endpoint}",
                json=body,
                headers=headers,
            )
            resp.raise_for_status()
            logger.info(f"QQ media sent: {media_path}")
        except Exception as e:
            logger.error(f"Failed to send QQ media {media_path}: {e}")

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

    async def test_connection(self) -> Dict[str, Any]:
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
