"""钉钉频道模块

使用 dingtalk-stream SDK 通过 WebSocket 长连接接收事件，无需公网 IP。
消息回复优先使用 sessionWebhook（更快），过期后自动降级到 OpenAPI。
钉钉 markdown 类型消息不支持真正的 @通知，仅在文本中显示 @昵称。
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from backend.modules.channels.base import BaseChannel, OutboundMessage

try:
    from dingtalk_stream import (
        DingTalkStreamClient,
        Credential,
        CallbackHandler,
        CallbackMessage,
        AckMessage,
    )
    from dingtalk_stream.chatbot import ChatbotMessage

    DINGTALK_AVAILABLE = True
except ImportError:
    DINGTALK_AVAILABLE = False
    CallbackHandler = object
    CallbackMessage = None
    AckMessage = None
    ChatbotMessage = None

# 消息类型显示映射
_MSG_TYPE_MAP = {
    "picture": "[图片]",
    "audio": "[语音]",
    "file": "[文件]",
}


# ------------------------------------------------------------------
# Stream 回调处理器
# ------------------------------------------------------------------


class DingTalkStreamHandler(CallbackHandler if DINGTALK_AVAILABLE else object):
    """钉钉 Stream SDK 回调处理器，解析入站消息并分发给 DingTalkChannel。"""

    def __init__(self, channel: "DingTalkChannel"):
        if DINGTALK_AVAILABLE:
            super().__init__()
        self.channel = channel

    async def process(self, message):
        """解析 Stream 回调消息，提取内容后交给 channel 处理。"""
        try:
            data = message.data
            if isinstance(data, str):
                data = json.loads(data)
            chatbot_msg = ChatbotMessage.from_dict(data)
            content = self._extract_content(chatbot_msg, data)

            if not content:
                logger.warning(f"Unsupported message type: {chatbot_msg.message_type}")
                return AckMessage.STATUS_OK, "OK"

            sender_id = chatbot_msg.sender_staff_id or chatbot_msg.sender_id
            sender_name = chatbot_msg.sender_nick or "Unknown"
            conversation_id = chatbot_msg.conversation_id or sender_id
            is_group = chatbot_msg.conversation_type == "2"

            session_webhook = chatbot_msg.session_webhook
            session_webhook_expired_time = chatbot_msg.session_webhook_expired_time
            if session_webhook:
                logger.info(
                    f"Got sessionWebhook for {sender_name} "
                    f"(expires: {session_webhook_expired_time})"
                )

            logger.info(
                f"DingTalk {'group' if is_group else 'private'}: "
                f"{sender_name}: {content[:50]}..."
            )

            task = asyncio.create_task(
                self.channel._on_message(
                    content=content,
                    sender_id=sender_id,
                    sender_name=sender_name,
                    conversation_id=conversation_id,
                    is_group=is_group,
                    session_webhook=session_webhook,
                    session_webhook_expired_time=session_webhook_expired_time,
                )
            )
            self.channel._background_tasks.add(task)

            def _task_done(t):
                self.channel._background_tasks.discard(t)
                if t.exception():
                    logger.error(f"Background task failed: {t.exception()}")

            task.add_done_callback(_task_done)
            return AckMessage.STATUS_OK, "OK"

        except Exception as e:
            logger.error(f"Error processing DingTalk message: {e}")
            return AckMessage.STATUS_OK, "Error"

    # ------------------------------------------------------------------
    # 内容提取
    # ------------------------------------------------------------------

    def _extract_content(self, chatbot_msg, raw_data: dict) -> str:
        """从 ChatbotMessage 中提取文本内容。"""
        if chatbot_msg.message_type == "text":
            return self._extract_text(chatbot_msg, raw_data)
        if chatbot_msg.message_type == "picture":
            return self._extract_image(chatbot_msg, raw_data)
        return _MSG_TYPE_MAP.get(chatbot_msg.message_type, "")

    @staticmethod
    def _extract_text(chatbot_msg, raw_data: dict) -> str:
        """提取文本消息内容。"""
        text = chatbot_msg.text
        if text and hasattr(text, "content") and text.content:
            return text.content.strip()
        raw_text = raw_data.get("text", {})
        if isinstance(raw_text, dict):
            return raw_text.get("content", "").strip()
        return ""

    @staticmethod
    def _extract_image(chatbot_msg, raw_data: dict) -> str:
        """提取图片消息的 downloadCode。"""
        download_code = None
        if hasattr(chatbot_msg, "image_content") and chatbot_msg.image_content:
            download_code = getattr(chatbot_msg.image_content, "download_code", None)
        if not download_code:
            raw_content = raw_data.get("content", {})
            if isinstance(raw_content, str):
                try:
                    raw_content = json.loads(raw_content)
                except json.JSONDecodeError:
                    raw_content = {}
            if isinstance(raw_content, dict):
                download_code = raw_content.get("downloadCode") or raw_content.get(
                    "pictureDownloadCode"
                )
        return f"[图片:{download_code}]" if download_code else "[图片]"


# ------------------------------------------------------------------
# 钉钉频道
# ------------------------------------------------------------------


class DingTalkChannel(BaseChannel):
    """钉钉频道

    通过 dingtalk-stream SDK 的 WebSocket 长连接收发消息。
    回复优先使用 sessionWebhook，过期后降级到 OpenAPI。
    """

    name = "dingtalk"

    def __init__(self, config: Any):
        super().__init__(config)
        self._client = None
        self._http: httpx.AsyncClient | None = None
        self._access_token: str | None = None
        self._token_expiry: float = 0
        self._old_api_token: str | None = None
        self._old_token_expiry: float = 0
        self._background_tasks: set[asyncio.Task] = set()
        # sessionWebhook 缓存：chat_id -> {url, expired_time, sender_staff_id}
        self._webhook_cache: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """启动钉钉机器人，断开后直接退出，由 manager 监督负责重连。"""
        if not DINGTALK_AVAILABLE:
            logger.error("DingTalk SDK not installed. Run: pip install dingtalk-stream")
            return

        if not self.config.client_id or not self.config.client_secret:
            logger.error("DingTalk credentials not configured")
            return

        self._running = True
        self._http = httpx.AsyncClient()
        logger.info(f"Initializing DingTalk Stream: {self.config.client_id[:12]}...")

        try:
            credential = Credential(self.config.client_id, self.config.client_secret)
            self._client = DingTalkStreamClient(credential)
            handler = DingTalkStreamHandler(self)
            self._client.register_callback_handler(ChatbotMessage.TOPIC, handler)
            logger.info("DingTalk bot connecting (Stream Mode WebSocket)...")
            await self._client.start()
        except Exception as e:
            logger.warning(f"DingTalk stream connection exited: {e}")

    async def stop(self) -> None:
        """停止钉钉机器人并清理资源。"""
        self._running = False
        if self._http:
            await self._http.aclose()
            self._http = None
        for task in self._background_tasks:
            task.cancel()
        self._background_tasks.clear()
        logger.info("DingTalk bot stopped")

    # ------------------------------------------------------------------
    # Token 管理
    # ------------------------------------------------------------------

    async def _get_access_token(self) -> str | None:
        """获取或刷新 Access Token（OpenAPI v1.0）。"""
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token

        if not self._http:
            return None

        try:
            resp = await self._http.post(
                "https://api.dingtalk.com/v1.0/oauth2/accessToken",
                json={
                    "appKey": self.config.client_id,
                    "appSecret": self.config.client_secret,
                },
            )
            resp.raise_for_status()
            res = resp.json()
            self._access_token = res.get("accessToken")
            self._token_expiry = time.time() + int(res.get("expireIn", 7200)) - 60
            return self._access_token
        except Exception as e:
            logger.error(f"Failed to get access token: {e}")
            return None

    async def _get_old_api_token(self) -> str | None:
        """获取旧版 API token（用于 oapi 媒体上传接口）。"""
        if self._old_api_token and time.time() < self._old_token_expiry:
            return self._old_api_token

        if not self._http:
            return None

        try:
            resp = await self._http.get(
                "https://oapi.dingtalk.com/gettoken",
                params={
                    "appkey": self.config.client_id,
                    "appsecret": self.config.client_secret,
                },
            )
            resp.raise_for_status()
            res = resp.json()
            if res.get("errcode") == 0:
                self._old_api_token = res.get("access_token")
                self._old_token_expiry = time.time() + int(res.get("expires_in", 7200)) - 60
                return self._old_api_token
            logger.error(f"Failed to get old API token: {res}")
            return None
        except Exception as e:
            logger.error(f"Error getting old API token: {e}")
            return None

    # ------------------------------------------------------------------
    # 图片 URL 获取
    # ------------------------------------------------------------------

    async def _get_image_url(self, download_code: str) -> str | None:
        """通过下载码获取图片 OSS URL。"""
        try:
            token = await self._get_access_token()
            if not token:
                return None

            resp = await self._http.post(
                "https://api.dingtalk.com/v1.0/robot/messageFiles/download",
                json={"downloadCode": download_code, "robotCode": self.config.client_id},
                headers={
                    "x-acs-dingtalk-access-token": token,
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code != 200:
                logger.error(f"Failed to get image URL: {resp.status_code}")
                return None

            download_url = resp.json().get("downloadUrl")
            if download_url:
                logger.info("Got image URL successfully")
            return download_url
        except Exception as e:
            logger.error(f"Error getting image URL: {e}")
            return None

    # ------------------------------------------------------------------
    # 出站消息发送
    # ------------------------------------------------------------------

    async def send(self, msg: OutboundMessage) -> None:
        """发送消息（优先 sessionWebhook，过期则降级到 OpenAPI）。"""
        if not self._http:
            logger.warning("HTTP client not initialized")
            return

        if msg.media:
            token = await self._get_access_token()
            if not token:
                logger.error("Failed to get access token for media send")
                return
            await self._send_with_media(msg, token)
            return

        if await self._send_via_webhook(msg):
            return

        await self._send_via_openapi(msg)

    async def _send_via_webhook(self, msg: OutboundMessage) -> bool:
        """通过 sessionWebhook 发送 markdown 回复，成功返回 True。"""
        webhook_info = self._webhook_cache.get(msg.chat_id)
        if not webhook_info:
            return False

        expired_time = webhook_info.get("expired_time", 0)
        if expired_time and time.time() * 1000 > expired_time:
            del self._webhook_cache[msg.chat_id]
            return False

        url = webhook_info["url"]
        sender_staff_id = webhook_info.get("sender_staff_id")

        try:
            text = msg.content
            if sender_staff_id:
                text = f"@{sender_staff_id}\n\n{text}"

            data = {
                "msgtype": "markdown",
                "markdown": {"title": "CountBot Reply", "text": text},
            }
            if sender_staff_id:
                data["at"] = {"atUserIds": [sender_staff_id]}

            resp = await self._http.post(url, json=data)
            if resp.status_code == 200:
                logger.info(f"Sent via sessionWebhook to {msg.chat_id}")
                return True
            logger.warning(f"sessionWebhook failed ({resp.status_code}), falling back to OpenAPI")
            return False
        except Exception as e:
            logger.warning(f"sessionWebhook error: {e}, falling back to OpenAPI")
            return False

    async def _send_via_openapi(self, msg: OutboundMessage) -> None:
        """通过 OpenAPI 发送消息（降级方式）。"""
        token = await self._get_access_token()
        if not token:
            logger.error("Failed to get access token")
            return

        headers = {"x-acs-dingtalk-access-token": token}
        is_group = msg.chat_id.startswith("cid") or "group" in msg.chat_id.lower()

        try:
            if is_group:
                url = "https://api.dingtalk.com/v1.0/robot/groupMessages/send"
                data = {
                    "robotCode": self.config.client_id,
                    "openConversationId": msg.chat_id,
                    "msgKey": "sampleMarkdown",
                    "msgParam": json.dumps({"text": msg.content, "title": "CountBot Reply"}),
                }
            else:
                url = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
                data = {
                    "robotCode": self.config.client_id,
                    "userIds": [msg.chat_id],
                    "msgKey": "sampleMarkdown",
                    "msgParam": json.dumps({"text": msg.content, "title": "CountBot Reply"}),
                }

            resp = await self._http.post(url, json=data, headers=headers)
            if resp.status_code != 200:
                logger.error(f"OpenAPI send failed: {resp.text}")
            else:
                logger.debug(f"Sent via OpenAPI to {msg.chat_id}")
        except Exception as e:
            logger.error(f"Error sending via OpenAPI: {e}")

    # ------------------------------------------------------------------
    # 媒体文件发送
    # ------------------------------------------------------------------

    async def _send_with_media(self, msg: OutboundMessage, token: str) -> None:
        """发送带媒体文件的消息。"""
        try:
            is_group = msg.chat_id.startswith("cid") or "group" in msg.chat_id.lower()
            for file_path in msg.media:
                await self._send_media_file(msg.chat_id, file_path, token, is_group)
            logger.info(f"Sent {len(msg.media)} media file(s)")
        except Exception as e:
            logger.error(f"Error sending media: {e}")

    async def _send_media_file(
        self, chat_id: str, file_path: str, token: str, is_group: bool
    ) -> None:
        """根据文件类型分发到图片或文件发送。"""
        if self._is_image_file(file_path):
            await self._send_image(chat_id, file_path, token, is_group)
        else:
            await self._send_file(chat_id, file_path, token, is_group)

    @staticmethod
    def _is_image_file(file_path: str) -> bool:
        """判断是否为图片文件。"""
        return Path(file_path).suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

    async def _send_image(
        self, chat_id: str, image_path: str, token: str, is_group: bool
    ) -> None:
        """上传并发送图片。"""
        try:
            file_path = Path(image_path)
            if not file_path.exists():
                logger.error(f"Image not found: {image_path}")
                return

            old_token = await self._get_old_api_token()
            if not old_token:
                logger.error("Failed to get old API token for image upload")
                return

            media_id = await self._upload_media(file_path, old_token, "image")
            if not media_id:
                logger.error(f"Failed to upload image: {image_path}")
                return

            headers = {"x-acs-dingtalk-access-token": token}
            msg_param = json.dumps({"photoURL": media_id})

            if is_group:
                url = "https://api.dingtalk.com/v1.0/robot/groupMessages/send"
                data = {
                    "robotCode": self.config.client_id,
                    "openConversationId": chat_id,
                    "msgKey": "sampleImageMsg",
                    "msgParam": msg_param,
                }
            else:
                url = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
                data = {
                    "robotCode": self.config.client_id,
                    "userIds": [chat_id],
                    "msgKey": "sampleImageMsg",
                    "msgParam": msg_param,
                }

            resp = await self._http.post(url, json=data, headers=headers)
            if resp.status_code != 200:
                logger.error(f"Image send failed: {resp.text}")
            else:
                logger.info(f"Image sent: {file_path.name}")
        except Exception as e:
            logger.error(f"Error sending image: {e}")

    async def _send_file(
        self, chat_id: str, file_path: str, token: str, is_group: bool
    ) -> None:
        """上传并发送文件。"""
        try:
            file = Path(file_path)
            if not file.exists():
                logger.error(f"File not found: {file_path}")
                return

            old_token = await self._get_old_api_token()
            if not old_token:
                logger.error("Failed to get old API token for file upload")
                return

            media_id = await self._upload_media(file, old_token, "file")
            if not media_id:
                logger.error(f"Failed to upload file: {file_path}")
                return

            headers = {"x-acs-dingtalk-access-token": token}
            msg_param = json.dumps({
                "mediaId": media_id,
                "fileName": file.name,
                "fileType": file.suffix.lstrip("."),
            })

            if is_group:
                url = "https://api.dingtalk.com/v1.0/robot/groupMessages/send"
                data = {
                    "robotCode": self.config.client_id,
                    "openConversationId": chat_id,
                    "msgKey": "sampleFile",
                    "msgParam": msg_param,
                }
            else:
                url = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
                data = {
                    "robotCode": self.config.client_id,
                    "userIds": [chat_id],
                    "msgKey": "sampleFile",
                    "msgParam": msg_param,
                }

            resp = await self._http.post(url, json=data, headers=headers)
            if resp.status_code != 200:
                logger.error(f"File send failed: {resp.text}")
            else:
                logger.info(f"File sent: {file.name}")
        except Exception as e:
            logger.error(f"Error sending file: {e}")

    async def _upload_media(
        self, file_path: Path, token: str, media_type: str = "image"
    ) -> str | None:
        """通过旧版 oapi 接口上传媒体文件，返回 media_id。"""
        try:
            mime = "image/png" if media_type == "image" else "application/octet-stream"
            with open(file_path, "rb") as f:
                files = {"media": (file_path.name, f, mime)}
                params = {"access_token": token, "type": media_type}
                resp = await self._http.post(
                    "https://oapi.dingtalk.com/media/upload", files=files, params=params
                )
                if resp.status_code == 200:
                    result = resp.json()
                    if result.get("errcode") == 0:
                        media_id = result.get("media_id")
                        logger.info(f"Uploaded {media_type}: {media_id}")
                        return media_id
                    logger.error(f"Upload failed: {result}")
                else:
                    logger.error(f"Upload error: {resp.status_code}")
        except Exception as e:
            logger.error(f"Error uploading {media_type}: {e}")
        return None

    # ------------------------------------------------------------------
    # 入站消息处理
    # ------------------------------------------------------------------

    async def _on_message(
        self,
        content: str,
        sender_id: str,
        sender_name: str,
        conversation_id: str,
        is_group: bool,
        session_webhook: str | None = None,
        session_webhook_expired_time: int | None = None,
    ) -> None:
        """处理入站消息，缓存 webhook 后转发到消息回调。"""
        try:
            chat_id = conversation_id if is_group else sender_id

            if session_webhook:
                self._webhook_cache[chat_id] = {
                    "url": session_webhook,
                    "expired_time": session_webhook_expired_time or 0,
                    "sender_staff_id": sender_id,
                }

            logger.info(
                f"Dispatching {'group' if is_group else 'private'} message "
                f"from {sender_name}"
            )

            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content=str(content),
                metadata={
                    "sender_name": sender_name,
                    "platform": "dingtalk",
                    "conversation_id": conversation_id,
                    "is_group": is_group,
                },
            )
        except Exception as e:
            logger.exception(f"Error handling message from {sender_name}: {e}")

    # ------------------------------------------------------------------
    # 连接测试
    # ------------------------------------------------------------------

    async def test_connection(self) -> dict[str, Any]:
        """测试钉钉连接（获取 access token 验证凭据）。"""
        if not self.config.client_id or not self.config.client_secret:
            return {"success": False, "message": "Client ID or Client Secret not configured"}

        if not DINGTALK_AVAILABLE:
            return {"success": False, "message": "DingTalk SDK not installed"}

        temp_http = None
        try:
            temp_http = httpx.AsyncClient()
            resp = await temp_http.post(
                "https://api.dingtalk.com/v1.0/oauth2/accessToken",
                json={
                    "appKey": self.config.client_id,
                    "appSecret": self.config.client_secret,
                },
            )
            resp.raise_for_status()
            token = resp.json().get("accessToken")

            if token:
                return {
                    "success": True,
                    "message": "DingTalk connection successful",
                    "bot_info": {
                        "client_id": self.config.client_id[:8] + "...",
                        "status": "connected",
                    },
                }
            return {"success": False, "message": "Failed to get access token from response"}
        except Exception as e:
            return {"success": False, "message": f"Connection test failed: {e}"}
        finally:
            if temp_http:
                await temp_http.aclose()

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def display_name(self) -> str:
        return "DingTalk"
