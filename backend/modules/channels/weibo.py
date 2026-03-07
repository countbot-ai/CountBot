"""微博频道模块

使用 WebSocket 长连接接收微博私信，支持文本、图片、文件消息。
通过微博龙虾助手获取 App ID 和 App Secret。

获取凭证步骤：
1. 私信 @微博龙虾助手
2. 发送 "连接龙虾"
3. 获取 AppId 和 AppSecret

实现方案：
- 全局 WebSocket 客户端缓存（模拟 openclaw-weibo）
- 持久连接保持活跃
- 定期心跳保活（30 秒间隔）
- 自动重连和 Token 刷新
"""

import asyncio
import base64
import json
import time
from pathlib import Path
from typing import Any, Optional

import httpx
import websockets
from loguru import logger

from backend.modules.channels.base import BaseChannel, OutboundMessage


# 全局 WebSocket 客户端缓存（每个账号一个连接）
_ws_clients: dict[str, websockets.WebSocketClientProtocol] = {}


class WeiboChannel(BaseChannel):
    """微博频道

    通过 WebSocket 长连接收发私信，支持文本、图片、文件。
    
    特点：
    - 使用全局 WebSocket 客户端缓存
    - 持久连接保持活跃
    - 定期心跳保活
    - 自动重连和 Token 刷新
    """

    name = "weibo"

    def __init__(self, config: Any):
        super().__init__(config)
        self._account_id = getattr(config, "account_id", "default")
        self._token: Optional[str] = None
        self._token_expires_at: float = 0
        self._reconnect_delay = 5
        self._max_reconnect_delay = 300
        self._heartbeat_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """启动微博机器人（WebSocket 长连接模式）"""
        if not self.config.app_id or not self.config.app_secret:
            logger.error("Weibo app_id and app_secret not configured")
            return

        self._running = True
        logger.info(f"[{self._account_id}] Starting Weibo channel...")

        # 主循环：自动重连
        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{self._account_id}] Weibo connection error: {e}")

            if not self._running:
                break

            logger.warning(
                f"[{self._account_id}] Weibo connection lost, "
                f"reconnecting in {self._reconnect_delay}s..."
            )
            await asyncio.sleep(self._reconnect_delay)

            # 指数退避
            self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

    async def stop(self) -> None:
        """停止微博机器人"""
        self._running = False
        
        # 取消心跳任务
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # 关闭 WebSocket 连接
        ws = _ws_clients.pop(self._account_id, None)
        if ws:
            try:
                await ws.close()
            except Exception as e:
                logger.warning(f"[{self._account_id}] Error closing WebSocket: {e}")
        
        logger.info(f"[{self._account_id}] Weibo bot stopped")

    async def test_connection(self) -> dict[str, Any]:
        """测试微博连接（验证凭据并获取 Token）"""
        if not self.config.app_id or not self.config.app_secret:
            return {
                "success": False,
                "message": "App ID and App Secret not configured"
            }

        try:
            # 尝试获取 Token 来验证凭据
            token_endpoint = getattr(
                self.config,
                "token_endpoint",
                "http://open-im.api.weibo.com/open/auth/ws_token",
            )

            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                response = await client.post(
                    token_endpoint,
                    json={
                        "app_id": self.config.app_id,
                        "app_secret": self.config.app_secret,
                    },
                )
                response.raise_for_status()
                data = response.json()

                if data.get("code") != 0:
                    return {
                        "success": False,
                        "message": f"Authentication failed: {data.get('msg', 'Unknown error')}"
                    }

                return {
                    "success": True,
                    "message": "Successfully connected to Weibo",
                    "token_info": {
                        "expires_in": data["data"].get("expire_in"),
                    }
                }

        except httpx.HTTPError as e:
            return {
                "success": False,
                "message": f"HTTP error: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Connection test failed: {str(e)}"
            }


    # ------------------------------------------------------------------
    # Token 管理
    # ------------------------------------------------------------------

    async def _get_valid_token(self) -> str:
        """获取或刷新 Token"""
        if self._token and time.time() < self._token_expires_at:
            return self._token

        logger.info(f"[{self._account_id}] Fetching Weibo access token...")
        token_endpoint = getattr(
            self.config,
            "token_endpoint",
            "http://open-im.api.weibo.com/open/auth/ws_token",
        )

        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            try:
                response = await client.post(
                    token_endpoint,
                    json={
                        "app_id": self.config.app_id,
                        "app_secret": self.config.app_secret,
                    },
                )
                response.raise_for_status()
                data = response.json()

                if data.get("code") != 0:
                    raise Exception(f"Token fetch failed: {data}")

                self._token = data["data"]["token"]
                expire_in = data["data"]["expire_in"]
                self._token_expires_at = time.time() + expire_in - 60  # 提前 60 秒刷新

                logger.info(
                    f"[{self._account_id}] Weibo token obtained (expires in {expire_in}s)"
                )
                return self._token

            except httpx.HTTPError as e:
                logger.error(f"[{self._account_id}] HTTP error fetching token: {e}")
                raise
            except Exception as e:
                logger.error(f"[{self._account_id}] Error fetching token: {e}")
                raise

    # ------------------------------------------------------------------
    # WebSocket 连接
    # ------------------------------------------------------------------

    async def _connect_and_listen(self) -> None:
        """建立 WebSocket 连接并监听消息"""
        token = await self._get_valid_token()
        ws_endpoint = getattr(
            self.config, "ws_endpoint", "ws://open-im.api.weibo.com/ws/stream"
        )
        url = f"{ws_endpoint}?app_id={self.config.app_id}&token={token}"

        logger.info(f"[{self._account_id}] Connecting to Weibo WebSocket...")

        async with websockets.connect(url) as ws:
            # 保存到全局缓存
            _ws_clients[self._account_id] = ws
            self._reconnect_delay = 5  # 重置退避时间
            logger.success(f"[{self._account_id}] Weibo WebSocket connected")

            # 接收连接确认
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(message)
                logger.info(f"[{self._account_id}] Connection confirmed: {data.get('type')}")
            except asyncio.TimeoutError:
                logger.warning(f"[{self._account_id}] No connection confirmation received")

            # 启动心跳任务
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))

            try:
                async for message in ws:
                    await self._handle_ws_message(message)
            except websockets.exceptions.ConnectionClosed as e:
                if e.code == 4004:
                    logger.warning(
                        f"[{self._account_id}] Weibo token expired, will refresh on reconnect"
                    )
                    self._token = None  # 强制刷新 Token
                else:
                    logger.warning(
                        f"[{self._account_id}] Weibo WebSocket closed: {e.code} {e.reason}"
                    )
            except Exception as e:
                logger.error(f"[{self._account_id}] Error in WebSocket loop: {e}")
                raise
            finally:
                # 清理心跳任务
                if self._heartbeat_task:
                    self._heartbeat_task.cancel()
                    try:
                        await self._heartbeat_task
                    except asyncio.CancelledError:
                        pass
                
                # 从缓存中移除
                _ws_clients.pop(self._account_id, None)

    async def _heartbeat_loop(self, ws: websockets.WebSocketClientProtocol) -> None:
        """心跳保活循环"""
        while self._running:
            try:
                await asyncio.sleep(30)
                await ws.send(json.dumps({"type": "ping"}))
                logger.debug(f"[{self._account_id}] Heartbeat sent")
            except Exception as e:
                logger.error(f"[{self._account_id}] Heartbeat error: {e}")
                break

    async def _handle_ws_message(self, raw_message: str) -> None:
        """处理 WebSocket 消息"""
        try:
            data = json.loads(raw_message)
            msg_type = data.get("type")

            if msg_type == "message":
                await self._process_inbound_message(data.get("payload", {}))
            elif msg_type == "pong":
                logger.debug(f"[{self._account_id}] Pong received")
            elif msg_type == "system":
                logger.debug(f"[{self._account_id}] System message: {data.get('payload')}")
            else:
                logger.debug(f"[{self._account_id}] Unknown message type: {msg_type}")

        except json.JSONDecodeError as e:
            logger.warning(f"[{self._account_id}] Failed to parse message: {e}")
        except Exception as e:
            logger.error(f"[{self._account_id}] Error handling message: {e}")

    # ------------------------------------------------------------------
    # 入站消息处理
    # ------------------------------------------------------------------

    async def _process_inbound_message(self, payload: dict) -> None:
        """处理入站消息"""
        try:
            message_id = payload.get("messageId", "")
            from_user_id = payload.get("fromUserId", "")
            text = payload.get("text", "")
            timestamp = payload.get("timestamp", int(time.time() * 1000))

            if not from_user_id:
                logger.warning(f"[{self._account_id}] Received message without fromUserId")
                return

            # 处理附件（图片/文件）
            media_files = []
            input_data = payload.get("input", [])

            if input_data:
                media_files = await self._process_attachments(input_data, message_id)

            # 如果有附件但没有文本，生成描述
            if media_files and not text:
                text = self._generate_attachment_description(media_files)

            logger.debug(
                f"[{self._account_id}] Message from {from_user_id}: {text[:50]}... "
                f"({len(media_files)} attachments)"
            )

            # 转发到消息处理器
            await self._handle_message(
                sender_id=from_user_id,
                chat_id=from_user_id,  # 微博私信是一对一
                content=text,
                media=media_files or None,
                metadata={
                    "message_id": message_id,
                    "timestamp": timestamp,
                    "platform": "weibo",
                },
            )

        except Exception as e:
            logger.error(f"[{self._account_id}] Error processing inbound message: {e}")

    async def _process_attachments(
        self, input_data: list, message_id: str
    ) -> list[str]:
        """处理消息附件（图片/文件）"""
        media_files = []

        try:
            for item in input_data:
                if item.get("type") != "message":
                    continue

                content_list = item.get("content", [])
                for content in content_list:
                    content_type = content.get("type")

                    if content_type in ("input_image", "input_file"):
                        file_path = await self._save_attachment(
                            content, message_id, content_type
                        )
                        if file_path:
                            media_files.append(file_path)

        except Exception as e:
            logger.error(f"Error processing attachments: {e}")

        return media_files

    async def _save_attachment(
        self, content: dict, message_id: str, content_type: str
    ) -> Optional[str]:
        """保存附件到本地"""
        try:
            source = content.get("source", {})
            if source.get("type") != "base64":
                logger.warning(f"Unsupported source type: {source.get('type')}")
                return None

            # 解码 base64 数据
            data_b64 = source.get("data", "")
            if not data_b64:
                return None

            file_data = base64.b64decode(data_b64)

            # 确定文件扩展名
            filename = content.get("filename", "")
            if not filename:
                ext = ".jpg" if content_type == "input_image" else ".bin"
                filename = f"{message_id}_{int(time.time())}{ext}"

            # 保存到临时目录
            save_dir = Path("data/temp/weibo")
            save_dir.mkdir(parents=True, exist_ok=True)
            file_path = save_dir / filename

            with open(file_path, "wb") as f:
                f.write(file_data)

            logger.info(f"Saved Weibo attachment: {file_path} ({len(file_data)} bytes)")
            return str(file_path)

        except Exception as e:
            logger.error(f"Error saving attachment: {e}")
            return None

    @staticmethod
    def _generate_attachment_description(media_files: list[str]) -> str:
        """生成附件描述文本"""
        descriptions = []
        for file_path in media_files:
            path = Path(file_path)
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}:
                descriptions.append(f"[图片: {path.name}]")
            else:
                descriptions.append(f"[文件: {path.name}]")
        return " ".join(descriptions)

    # ------------------------------------------------------------------
    # 出站消息发送
    # ------------------------------------------------------------------

    async def send(self, msg: OutboundMessage) -> None:
        """发送消息到微博"""
        ws = _ws_clients.get(self._account_id)
        if not ws:
            logger.warning(f"[{self._account_id}] WebSocket not connected")
            return

        try:
            # 如果有媒体文件，发送带附件的消息
            if msg.media:
                await self._send_with_media(msg, ws)
            else:
                await self._send_text(msg, ws)

        except Exception as e:
            logger.error(f"[{self._account_id}] Error sending message: {e}")

    async def _send_text(self, msg: OutboundMessage, ws: websockets.WebSocketClientProtocol) -> None:
        """发送纯文本消息"""
        message_id = f"msg_{int(time.time() * 1000)}"

        payload = {
            "type": "send_message",
            "payload": {
                "toUserId": msg.chat_id,
                "text": msg.content,
                "messageId": message_id,
                "chunkId": 0,
                "done": True,
            },
        }

        await ws.send(json.dumps(payload))
        logger.debug(f"[{self._account_id}] Sent text message to {msg.chat_id}")
