"""Telegram 频道模块

使用 python-telegram-bot 库通过长轮询模式接收消息，无需 webhook 或公网 IP。
python-telegram-bot 内置自动重连机制，无需额外处理。
"""

import asyncio
from typing import Any

from loguru import logger

from backend.modules.channels.base import BaseChannel, OutboundMessage


class TelegramChannel(BaseChannel):
    """Telegram 频道

    通过长轮询模式收发消息，支持私聊和群聊。
    python-telegram-bot 内置连接管理和自动重连。
    """

    name = "telegram"

    def __init__(self, config: Any):
        super().__init__(config)
        self._app = None
        self._chat_ids: dict[str, int] = {}

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """启动 Telegram 机器人。"""
        if not self.config.token:
            logger.error("Telegram bot token not configured")
            return

        try:
            from telegram import BotCommand, Update
            from telegram.ext import (
                Application,
                CommandHandler,
                MessageHandler,
                filters,
                ContextTypes,
            )
        except ImportError:
            logger.error("python-telegram-bot not installed. Run: pip install python-telegram-bot")
            return

        self._running = True

        builder = Application.builder().token(self.config.token)
        if hasattr(self.config, "proxy") and self.config.proxy:
            builder = builder.proxy(self.config.proxy).get_updates_proxy(self.config.proxy)

        self._app = builder.build()
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("help", self._on_help))
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message)
        )

        logger.info("Starting Telegram bot (polling mode)...")
        await self._app.initialize()
        await self._app.start()

        bot_info = await self._app.bot.get_me()
        logger.info(f"Telegram bot @{bot_info.username} connected")

        try:
            commands = [
                BotCommand("start", "Start the bot"),
                BotCommand("help", "Show help message"),
            ]
            await self._app.bot.set_my_commands(commands)
            logger.debug("Bot commands registered")
        except Exception as e:
            logger.warning(f"Failed to register bot commands: {e}")

        await self._app.updater.start_polling(
            allowed_updates=["message"], drop_pending_updates=True
        )

        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """停止 Telegram 机器人。"""
        self._running = False
        if self._app:
            logger.info("Stopping Telegram bot...")
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._app = None

    # ------------------------------------------------------------------
    # 出站消息发送
    # ------------------------------------------------------------------

    async def send(self, msg: OutboundMessage) -> None:
        """发送消息到 Telegram，markdown 失败自动降级为纯文本。"""
        if not self._app:
            logger.warning("Telegram bot not running")
            return

        try:
            chat_id = int(msg.chat_id)
            await self._app.bot.send_message(
                chat_id=chat_id, text=msg.content, parse_mode="Markdown"
            )
        except ValueError:
            logger.error(f"Invalid chat_id: {msg.chat_id}")
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            try:
                await self._app.bot.send_message(chat_id=int(msg.chat_id), text=msg.content)
            except Exception as e2:
                logger.error(f"Failed to send plain text: {e2}")

    # ------------------------------------------------------------------
    # 入站消息处理
    # ------------------------------------------------------------------

    async def _on_start(self, update, context) -> None:
        """处理 /start 命令。"""
        if not update.message or not update.effective_user:
            return

        user = update.effective_user
        await update.message.reply_text(
            f"Hi {user.first_name}! I'm your AI assistant.\n\n"
            "Send me a message and I'll respond!\n"
            "Type /help to see available commands."
        )

    async def _on_help(self, update, context) -> None:
        """处理 /help 命令。"""
        if not update.message:
            return

        await update.message.reply_text(
            "*Available Commands*\n\n"
            "/start — Start the bot\n"
            "/help — Show this help message\n\n"
            "Just send me a text message to chat!",
            parse_mode="Markdown",
        )

    async def _on_message(self, update, context) -> None:
        """处理入站文本消息。"""
        if not update.message or not update.effective_user:
            return

        message = update.message
        user = update.effective_user
        chat_id = message.chat_id

        sender_id = str(user.id)
        if user.username:
            sender_id = f"{sender_id}|{user.username}"

        self._chat_ids[sender_id] = chat_id
        content = message.text or "[empty message]"

        logger.debug(f"Telegram message from {sender_id}: {content[:50]}...")

        await self._handle_message(
            sender_id=sender_id,
            chat_id=str(chat_id),
            content=content,
            metadata={
                "message_id": message.message_id,
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "is_group": message.chat.type != "private",
            },
        )

    # ------------------------------------------------------------------
    # 连接测试
    # ------------------------------------------------------------------

    async def test_connection(self) -> dict[str, Any]:
        """测试 Telegram 连接（验证 bot token）。"""
        if not self.config.token:
            return {"success": False, "message": "Token not configured"}

        try:
            from telegram import Bot
            from telegram.request import HTTPXRequest

            kwargs = {}
            if hasattr(self.config, "proxy") and self.config.proxy:
                kwargs["request"] = HTTPXRequest(proxy=self.config.proxy)

            bot = Bot(token=self.config.token, **kwargs)
            bot_info = await bot.get_me()
            await bot.close()

            return {
                "success": True,
                "message": f"Connected to @{bot_info.username}",
                "bot_info": {
                    "username": bot_info.username,
                    "first_name": bot_info.first_name,
                    "id": bot_info.id,
                },
            }
        except ImportError:
            return {"success": False, "message": "python-telegram-bot not installed"}
        except Exception as e:
            return {"success": False, "message": f"Connection failed: {e}"}

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def display_name(self) -> str:
        return "Telegram"
