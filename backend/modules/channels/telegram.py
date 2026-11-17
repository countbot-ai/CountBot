"""Telegram 频道：httpx 直连 Bot API 长轮询收发消息，无需 webhook/公网 IP。

直接调用 Telegram Bot HTTP API（getMe / setMyCommands / getUpdates /
sendMessage），不依赖 python-telegram-bot SDK：桌面版打包只保留 httpx，
省去 SDK 及其依赖的体积。长轮询由独立任务承载，网络错误按固定间隔重试。
"""

import asyncio
from typing import Any, Dict, Optional

import httpx
from loguru import logger

from backend.modules.channels.base import BaseChannel, OutboundMessage


class TelegramChannel(BaseChannel):
    """Telegram 频道：长轮询收发消息，支持私聊与群聊。"""

    name = "telegram"

    # 长轮询挂起时长要小于 HTTP 读超时，避免客户端在网络空闲时先断开。
    _POLL_TIMEOUT_SECONDS = 30
    _REQUEST_TIMEOUT_SECONDS = 35.0
    _RETRY_DELAY_SECONDS = 5.0
    _API_BASE = "https://api.telegram.org"

    def __init__(self, config: Any):
        super().__init__(config)
        self._client: Optional[httpx.AsyncClient] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._offset = 0
        self._chat_ids: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Bot API 基础访问
    # ------------------------------------------------------------------

    def _build_client(self) -> httpx.AsyncClient:
        kwargs: Dict[str, Any] = {"timeout": httpx.Timeout(self._REQUEST_TIMEOUT_SECONDS)}
        proxy = getattr(self.config, "proxy", None)
        if proxy:
            kwargs["proxy"] = proxy
        return httpx.AsyncClient(**kwargs)

    def _api_url(self, method: str) -> str:
        return f"{self._API_BASE}/bot{self.config.token}/{method}"

    async def _call(
        self, method: str, *, client: Optional[httpx.AsyncClient] = None, **params: Any
    ) -> Any:
        http = client or self._client
        if http is None:
            raise RuntimeError("Telegram HTTP client is not initialized")
        response = await http.post(self._api_url(method), json=params)
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(
                f"Telegram API {method} failed: {data.get('description') or data}"
            )
        return data.get("result")

    async def _send_text(
        self, chat_id: int, text: str, parse_mode: Optional[str] = None
    ) -> None:
        params: Dict[str, Any] = {"chat_id": chat_id, "text": text}
        if parse_mode:
            params["parse_mode"] = parse_mode
        await self._call("sendMessage", **params)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """启动 Telegram 机器人。"""
        if not self.config.token:
            logger.error("Telegram bot token not configured")
            return

        self._running = True
        self.set_runtime_state(self.RUNTIME_CONNECTING)
        self._client = self._build_client()
        self._offset = 0

        bot_info = await self._call("getMe")
        logger.info(f"Telegram bot @{bot_info.get('username')} connected")

        try:
            await self._call(
                "setMyCommands",
                commands=[
                    {"command": "start", "description": "Start the bot"},
                    {"command": "help", "description": "Show help message"},
                ],
            )
            logger.debug("Bot commands registered")
        except Exception as e:
            logger.warning(f"Failed to register bot commands: {e}")

        logger.info("Starting Telegram bot (polling mode)...")
        self._poll_task = asyncio.create_task(self._poll_loop())
        self.set_runtime_state(self.RUNTIME_RUNNING, reconnect_attempts=0)

        while self._running:
            await asyncio.sleep(1)

        self.set_runtime_state(self.RUNTIME_STOPPED)

    async def _poll_loop(self) -> None:
        """getUpdates 长轮询循环；网络错误记日志并延时重试。"""
        while self._running:
            try:
                updates = await self._call(
                    "getUpdates",
                    offset=self._offset,
                    timeout=self._POLL_TIMEOUT_SECONDS,
                    allowed_updates=["message"],
                    drop_pending_updates=True,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not self._running:
                    break
                logger.warning(f"Telegram polling error: {exc}; retrying...")
                await asyncio.sleep(self._RETRY_DELAY_SECONDS)
                continue

            for update in updates:
                self._offset = max(self._offset, int(update.get("update_id", 0)) + 1)
                try:
                    await self._process_update(update)
                except Exception as exc:
                    logger.error(f"Error processing Telegram update: {exc}")
            # 每轮显式让出事件循环，保证 stop() 的取消请求能送达本任务。
            await asyncio.sleep(0)

    async def stop(self) -> None:
        """停止 Telegram 机器人。"""
        self.set_runtime_state(self.RUNTIME_STOPPING)
        self._running = False
        if self._poll_task and self._poll_task is not asyncio.current_task():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        self._poll_task = None
        if self._client:
            await self._client.aclose()
            self._client = None
        self.set_runtime_state(self.RUNTIME_STOPPED)

    # ------------------------------------------------------------------
    # 出站消息发送
    # ------------------------------------------------------------------

    async def send(self, msg: OutboundMessage) -> None:
        """发送消息到 Telegram，markdown 失败自动降级为纯文本。"""
        if not self._client:
            logger.warning("Telegram bot not running")
            return

        try:
            chat_id = int(msg.chat_id)
            await self._send_text(chat_id, msg.content, parse_mode="Markdown")
        except ValueError:
            logger.error(f"Invalid chat_id: {msg.chat_id}")
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            try:
                await self._send_text(int(msg.chat_id), msg.content)
            except Exception as e2:
                logger.error(f"Failed to send plain text: {e2}")

    # ------------------------------------------------------------------
    # 入站消息处理
    # ------------------------------------------------------------------

    async def _process_update(self, update: Dict[str, Any]) -> None:
        """分发单条 update：/start、/help 走命令应答，其余文本进 Agent。"""
        message = update.get("message")
        if not message:
            return
        user = message.get("from")
        if not user:
            return

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        if chat_id is None:
            return
        self._chat_ids[str(user.get("id"))] = chat_id

        text = message.get("text") or ""
        if text.startswith("/"):
            command = text.split()[0].split("@", 1)[0][1:]
            if command == "start":
                await self._send_text(chat_id, self._start_reply(user.get("first_name")))
            elif command == "help":
                try:
                    await self._send_text(chat_id, self._help_reply(), parse_mode="Markdown")
                except Exception:
                    await self._send_text(chat_id, self._help_reply())
            # 其余命令与 python-telegram-bot 的默认行为一致：静默忽略。
            return

        await self._on_message(message, user, chat)

    def _start_reply(self, first_name: Optional[str] = None) -> str:
        greeting = f"Hi {first_name}!" if first_name else "Hi there!"
        return (
            f"{greeting} I'm your AI assistant.\n\n"
            "Send me a message and I'll respond!\n"
            "Type /help to see available commands."
        )

    def _help_reply(self) -> str:
        return (
            "*Available Commands*\n\n"
            "/start — Start the bot\n"
            "/help — Show this help message\n\n"
            "Just send me a text message to chat!"
        )

    async def _on_message(
        self, message: Dict[str, Any], user: Dict[str, Any], chat: Dict[str, Any]
    ) -> None:
        """处理入站文本消息。"""
        sender_id = str(user.get("id"))
        if user.get("username"):
            sender_id = f"{sender_id}|{user['username']}"

        self._chat_ids[sender_id] = chat["id"]
        content = message.get("text") or "[empty message]"

        logger.debug(f"Telegram message from {sender_id}: {content[:50]}...")

        await self._handle_message(
            sender_id=sender_id,
            chat_id=str(chat["id"]),
            content=content,
            metadata={
                "message_id": message.get("message_id"),
                "user_id": user.get("id"),
                "username": user.get("username"),
                "first_name": user.get("first_name"),
                "is_group": chat.get("type") != "private",
            },
        )

    # ------------------------------------------------------------------
    # 连接测试
    # ------------------------------------------------------------------

    async def test_connection(self) -> Dict[str, Any]:
        """测试 Telegram 连接（验证 bot token）。"""
        if not self.config.token:
            return {"success": False, "message": "Token not configured"}

        try:
            async with self._build_client() as client:
                bot_info = await self._call("getMe", client=client)

            return {
                "success": True,
                "message": f"Connected to @{bot_info.get('username')}",
                "bot_info": {
                    "username": bot_info.get("username"),
                    "first_name": bot_info.get("first_name"),
                    "id": bot_info.get("id"),
                },
            }
        except Exception as e:
            return {"success": False, "message": f"Connection failed: {e}"}

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def display_name(self) -> str:
        return "Telegram"
