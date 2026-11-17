"""按机器人账号归属把入站消息路由到管理员或普通用户的处理器。"""

from __future__ import annotations

import asyncio
from typing import Dict, Optional

from loguru import logger

from backend.modules.channels.base import InboundMessage
from backend.modules.channels.handler import ChannelMessageHandler, _log_handle_task_exception
from backend.modules.config.loader import config_loader


def resolve_account_owner(channel: str, account_id: Optional[str]) -> Optional[str]:
    """解析渠道账号归属；管理员账号返回 None。"""
    channel_config = getattr(config_loader.config.channels, channel, None)
    if channel_config is None:
        return None

    target = str(account_id or "default")
    top_id = str(getattr(channel_config, "account_id", "default") or "default")
    if target == top_id:
        return getattr(channel_config, "owner_id", None)

    accounts = getattr(channel_config, "accounts", {}) or {}
    account = accounts.get(target)
    if account is None:
        return None
    return getattr(account, "owner_id", None)


class ChannelHandlerRouter:
    """管理员处理器 + 按 owner 懒加载的用户处理器。"""

    def __init__(self, admin_handler: ChannelMessageHandler) -> None:
        self._admin = admin_handler
        self.bus = admin_handler.bus
        self._user_handlers: Dict[str, tuple[object, ChannelMessageHandler]] = {}

    def __getattr__(self, name):
        return getattr(self._admin, name)

    async def start_processing(self) -> None:
        """从消息总线消费入站消息并按账号归属分发。"""
        logger.info("Message processing loop started")
        consecutive_errors = 0
        max_consecutive_errors = 10

        while True:
            try:
                msg = await self.bus.consume_inbound()
                consecutive_errors = 0
                task = asyncio.create_task(self.handle_message(msg))
                task.add_done_callback(_log_handle_task_exception)
            except Exception as exc:
                consecutive_errors += 1
                logger.error(
                    f"Processing loop error (consecutive: {consecutive_errors}): {exc}"
                )
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(
                        f"Too many consecutive errors ({consecutive_errors}), restarting loop..."
                    )
                    consecutive_errors = 0
                    await asyncio.sleep(5)
                else:
                    await asyncio.sleep(1)

    async def handle_message(self, msg: InboundMessage) -> None:
        account_id = str((msg.metadata or {}).get("account_id") or "default")
        owner_id = resolve_account_owner(msg.channel, account_id)
        if not owner_id:
            await self._admin.handle_message(msg)
            return

        handler = await self._get_user_handler(owner_id)
        if handler is None:
            logger.warning(
                f"[{msg.channel}] Ignored message for unavailable user {owner_id}"
            )
            return
        await handler.handle_message(msg)

    async def _get_user_handler(self, owner_id: str) -> Optional[ChannelMessageHandler]:
        from backend.database import AsyncSessionLocal
        from backend.models.user import User
        from backend.modules.multiuser.identity import user_to_auth_user
        from backend.modules.multiuser.runtime import user_runtime_manager

        async with AsyncSessionLocal() as db:
            user = await db.get(User, owner_id)
        if user is None or user.status != "active":
            return None

        runtime = await user_runtime_manager.get(user_to_auth_user(user))
        cached = self._user_handlers.get(owner_id)
        if cached is not None and cached[0] is runtime:
            return cached[1]

        handler = ChannelMessageHandler.for_runtime(
            runtime,
            bus=self.bus,
            rate_limiter=self._admin.rate_limiter,
            max_history_messages=self._admin.max_history_messages,
        )
        if self._admin.channel_manager is not None:
            handler.set_channel_manager(self._admin.channel_manager)
        self._user_handlers[owner_id] = (runtime, handler)
        return handler

    def reload_config(self, *args, **kwargs) -> None:
        self._admin.reload_config(*args, **kwargs)
        self._user_handlers.clear()

    def set_channel_manager(self, manager) -> None:
        self._admin.set_channel_manager(manager)
        for _, handler in self._user_handlers.values():
            handler.channel_manager = manager

    async def cancel_task(self, session_id: str) -> bool:
        cancelled = await self._admin.cancel_task(session_id)
        for _, handler in self._user_handlers.values():
            if await handler.cancel_task(session_id):
                cancelled = True
        return cancelled
