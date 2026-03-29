"""飞书频道模块

使用 lark-oapi SDK 通过 WebSocket 长连接接收事件，无需公网 IP。
WebSocket 连接运行在独立子进程中，通过 multiprocessing.Queue 通信。
支持文本、图片、文件消息，以及 markdown + 表格的卡片消息。
"""

import asyncio
import json
import re
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from multiprocessing import Process, Queue
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from backend.modules.channels.base import BaseChannel, OutboundMessage
from backend.modules.channels.media_utils import (
    format_inbound_media_text,
    save_bytes_to_temp,
)

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        CreateMessageRequest,
        CreateMessageRequestBody,
        CreateMessageReactionRequest,
        CreateMessageReactionRequestBody,
        CreateImageRequest,
        CreateImageRequestBody,
        PatchMessageRequest,
        PatchMessageRequestBody,
        Emoji,
    )
    from lark_oapi.api.cardkit.v1 import (
        Card as CardKitCard,
        ContentCardElementRequest,
        ContentCardElementRequestBody,
        CreateCardRequest,
        CreateCardRequestBody,
        SettingsCardRequest,
        SettingsCardRequestBody,
        UpdateCardRequest,
        UpdateCardRequestBody,
    )

    FEISHU_AVAILABLE = True
    FEISHU_CARDKIT_AVAILABLE = True
except ImportError:
    FEISHU_AVAILABLE = False
    FEISHU_CARDKIT_AVAILABLE = False
    lark = None
    Emoji = None

# 消息类型显示映射
_MSG_TYPE_MAP = {
    "image": "[图片]",
    "audio": "[语音]",
    "file": "[文件]",
    "sticker": "[表情]",
}

_STREAMING_ELEMENT_ID = "streaming_content"
_STREAM_FLUSH_INTERVAL_MS = 200
_ABORT_COMMANDS = {"/stop", "/cancel"}
_UNAVAILABLE_HINTS = (
    "message has been deleted",
    "message has been recalled",
    "message not found",
    "message not exist",
    "card not found",
    "resource not found",
    "entity not found",
    "invalid message_id",
    "invalid card_id",
)


class FeishuStreamPhase(str, Enum):
    """飞书流式回复的显式状态机阶段。"""

    IDLE = "idle"
    CREATING = "creating"
    STREAMING = "streaming"
    COMPLETED = "completed"
    ABORTED = "aborted"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass
class FeishuStreamState:
    """单条飞书流式回复的运行时状态。"""

    source_message_id: str
    chat_key: str
    reply_to: str
    receive_id_type: str
    phase: FeishuStreamPhase = FeishuStreamPhase.IDLE
    mode: str = "patch"
    card_id: Optional[str] = None
    feishu_message_id: Optional[str] = None
    accumulated_text: str = ""
    last_flushed_text: str = ""
    last_update_ms: float = 0.0
    version: int = 0
    flushed_version: int = 0
    sequence: int = 1
    final_requested: bool = False
    terminal_reason: Optional[str] = None
    flush_task: Optional[asyncio.Task] = None
    flush_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def is_terminal(self) -> bool:
        return self.phase in {
            FeishuStreamPhase.COMPLETED,
            FeishuStreamPhase.ABORTED,
            FeishuStreamPhase.UNAVAILABLE,
            FeishuStreamPhase.FAILED,
        }


class FeishuChannel(BaseChannel):
    """飞书频道

    通过独立子进程运行 WebSocket 连接，避免事件循环冲突。
    支持文本、图片、文件消息收发，出站消息使用卡片格式。
    """

    name = "feishu"

    # markdown 表格匹配正则
    _TABLE_RE = re.compile(
        r"((?:^[ \t]*\|.+\|[ \t]*\n)"
        r"(?:^[ \t]*\|[-:\s|]+\|[ \t]*\n)"
        r"(?:^[ \t]*\|.+\|[ \t]*\n?)+)",
        re.MULTILINE,
    )

    def __init__(self, config: Any):
        super().__init__(config)
        self._client = None
        self._ws_process: Optional[Process] = None
        self._message_queue: Optional[Queue] = None
        self._processed_ids: OrderedDict[str, None] = OrderedDict()
        self._terminal_stream_ids: OrderedDict[str, None] = OrderedDict()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stream_states: Dict[str, FeishuStreamState] = {}
        self._active_streams_by_chat: Dict[str, FeishuStreamState] = {}

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """启动飞书机器人（WebSocket 子进程模式）。"""
        if not FEISHU_AVAILABLE:
            logger.error("Feishu SDK not installed. Run: pip install lark-oapi")
            return

        if not self.config.app_id or not self.config.app_secret:
            logger.error("Feishu app_id and app_secret not configured")
            return

        self._running = True
        self._loop = asyncio.get_running_loop()

        self._client = (
            lark.Client.builder()
            .app_id(self.config.app_id)
            .app_secret(self.config.app_secret)
            .log_level(lark.LogLevel.INFO)
            .build()
        )

        from multiprocessing import get_context

        ctx = get_context("spawn")
        self._message_queue = ctx.Queue(maxsize=1000)

        from backend.modules.channels.feishu_websocket_worker import run_worker

        self._ws_process = ctx.Process(
            target=run_worker,
            args=(self.config.app_id, self.config.app_secret, self._message_queue),
            daemon=True,
            name="feishu-websocket-worker",
        )
        self._ws_process.start()
        logger.info(f"Feishu WebSocket worker started (PID: {self._ws_process.pid})")

        asyncio.create_task(self._read_ws_messages())

        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """停止飞书机器人。"""
        self._running = False

        if self._ws_process:
            try:
                logger.info("Terminating WebSocket worker process...")
                self._ws_process.terminate()
                self._ws_process.join(timeout=5)
                if self._ws_process.is_alive():
                    logger.warning("Worker did not terminate, killing...")
                    self._ws_process.kill()
                    self._ws_process.join(timeout=2)
                logger.info("WebSocket worker process stopped")
            except Exception as e:
                logger.error(f"Error stopping WebSocket process: {e}")

        if self._message_queue:
            try:
                while not self._message_queue.empty():
                    try:
                        self._message_queue.get_nowait()
                    except Exception:
                        break
                self._message_queue.close()
                self._message_queue.join_thread()
            except Exception as e:
                logger.debug(f"Error cleaning up queue: {e}")

        logger.info("Feishu bot stopped")

    # ------------------------------------------------------------------
    # 消息队列读取
    # ------------------------------------------------------------------

    async def _read_ws_messages(self) -> None:
        """从 WebSocket 子进程的队列读取消息。"""
        if not self._message_queue:
            return

        logger.info("Message queue reader started")
        try:
            while self._running:
                try:
                    msg_data = await asyncio.get_running_loop().run_in_executor(
                        None, lambda: self._message_queue.get(timeout=1.0)
                    )
                    if msg_data and msg_data.get("type") == "message":
                        await self._process_message(msg_data)
                except Exception as e:
                    if "Empty" not in str(e) and "timeout" not in str(e).lower():
                        logger.debug(f"Queue read error: {e}")
                    await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Message queue reader error: {e}")
        finally:
            logger.info("Message queue reader stopped")

    # ------------------------------------------------------------------
    # 入站消息处理
    # ------------------------------------------------------------------

    async def _process_message(self, msg_data: dict) -> None:
        """处理来自 WebSocket 子进程的消息"""
        try:
            message_id = msg_data["message_id"]

            # 消息去重
            if message_id in self._processed_ids:
                return
            self._processed_ids[message_id] = None
            while len(self._processed_ids) > 1000:
                self._processed_ids.popitem(last=False)

            sender_id = msg_data["sender_id"]
            sender_name = msg_data.get("sender_name") or sender_id
            chat_id = msg_data["chat_id"]
            chat_type = msg_data["chat_type"]
            msg_type = msg_data["msg_type"]

            await self._add_reaction(message_id, "THUMBSUP")

            media_files = []

            if msg_type == "text":
                try:
                    content = json.loads(msg_data["content"]).get("text", "")
                except json.JSONDecodeError:
                    content = msg_data["content"] or ""
            elif msg_type in {"image", "file", "audio", "video", "media", "sticker"}:
                content, media_files = await self._handle_media_message(
                    msg_type, msg_data["content"], message_id
                )
            else:
                content = _MSG_TYPE_MAP.get(msg_type, f"[{msg_type}]")

            if not content:
                return

            reply_to = chat_id if chat_type == "group" else sender_id
            receive_id_type = "chat_id" if chat_type == "group" else "open_id"
            chat_key = self._build_stream_chat_key(reply_to, receive_id_type)

            if self._is_abort_command(content):
                await self._abort_active_stream_fast(chat_key, trigger_text=content)

            progressive_stream = {
                "parts": [],
                "reasoning_parts": [],
                "sent": False,
                "aborted": False,
                "state": None,
                "progress_lines": [],
            }

            async def ensure_progress_state() -> Optional[FeishuStreamState]:
                state = progressive_stream["state"]
                if state and not state.is_terminal:
                    return state

                state = await self._create_stream_state(
                    source_message_id=message_id,
                    chat_key=chat_key,
                    chat_id=reply_to,
                    receive_id_type=receive_id_type,
                )
                if not state:
                    return None

                self._stream_states[message_id] = state
                self._active_streams_by_chat[chat_key] = state
                progressive_stream["state"] = state
                return state

            async def push_progress_line(line: str) -> None:
                if not line or progressive_stream["sent"] or progressive_stream["aborted"]:
                    return

                lines = progressive_stream["progress_lines"]
                if lines and lines[-1] == line:
                    return

                lines.append(line)
                state = await ensure_progress_state()
                if not state:
                    return

                state.accumulated_text = self._render_progress_text(lines)
                state.version += 1
                self._ensure_stream_flush_task(state)

            async def tool_event_handler(event_type: str, payload: Dict[str, Any]) -> None:
                line = self._build_tool_progress_line(event_type, payload)
                if line:
                    await push_progress_line(line)

            async def stream_handler(
                text_chunk: str,
                is_final: bool = False,
                is_reasoning: bool = False,
            ):
                """飞书渠道仅展示工具进度，最终统一覆盖为完整回复。"""
                if progressive_stream["sent"] or progressive_stream["aborted"]:
                    return

                if is_reasoning and text_chunk:
                    progressive_stream["reasoning_parts"].append(text_chunk)
                elif text_chunk:
                    progressive_stream["parts"].append(text_chunk)

                if not is_final:
                    return

                final_text = self._compose_reasoning_markdown(
                    "".join(progressive_stream["reasoning_parts"]),
                    "".join(progressive_stream["parts"]),
                )
                if not final_text:
                    final_text = "抱歉，未能生成回复，请稍后重试。"

                state = progressive_stream["state"]
                if state and not state.is_terminal:
                    state.accumulated_text = final_text
                    state.version += 1
                    state.final_requested = True
                    self._transition_stream_state(
                        state,
                        FeishuStreamPhase.COMPLETED,
                        "final_reply",
                        terminal_reason="final_reply",
                    )
                    self._ensure_stream_flush_task(state)
                    flush_task = state.flush_task
                    if flush_task and not flush_task.done():
                        await flush_task

                    if state.phase in {FeishuStreamPhase.UNAVAILABLE, FeishuStreamPhase.FAILED}:
                        await self._send_card(reply_to, final_text, receive_id_type)
                else:
                    await self._send_card(reply_to, final_text, receive_id_type)

                progressive_stream["sent"] = True
                logger.info(f"[Feishu] Final reply sent for {message_id}")

            async def abort_stream_handler() -> None:
                if progressive_stream["sent"] or progressive_stream["aborted"]:
                    return
                progressive_stream["aborted"] = True
                state = progressive_stream["state"]
                if state and not state.is_terminal:
                    await self._abort_stream_state(state, reason="abort_handler")
                else:
                    await self._send_card(reply_to, "已停止生成。", receive_id_type)
                logger.info(f"[Feishu] Abort reply sent for {message_id}")

            metadata = {
                "message_id": message_id,
                "sender_name": sender_name,
                "chat_type": chat_type,
                "msg_type": msg_type,
                "_stream_handler": stream_handler,
                "_stream_abort_handler": abort_stream_handler,
                "_tool_event_handler": tool_event_handler,
            }

            await self._handle_message(
                sender_id=sender_id,
                chat_id=reply_to,
                content=content,
                media=media_files or None,
                metadata=metadata,
            )
        except Exception as e:
            logger.error(f"Error processing Feishu message: {e}")

    @staticmethod
    def _build_stream_chat_key(chat_id: str, receive_id_type: str) -> str:
        """生成单聊/群聊维度的流式回复索引键。"""
        return f"{receive_id_type}:{chat_id}"

    @staticmethod
    def _is_abort_command(content: str) -> bool:
        """仅对显式停止命令走 abort fast-path，避免误伤普通文本。"""
        return content.strip().lower() in _ABORT_COMMANDS

    @staticmethod
    def _truncate_progress_text(value: Any, limit: int = 80) -> str:
        text = str(value or "").strip().replace("\n", " ")
        if len(text) > limit:
            return text[: limit - 3] + "..."
        return text

    def _build_tool_progress_line(self, event_type: str, payload: Dict[str, Any]) -> Optional[str]:
        """将工具/工作流事件映射为适合飞书单消息流式展示的简短进度文本。"""
        if event_type == "tool_call":
            tool_name = self._truncate_progress_text(payload.get("tool_name") or "unknown")
            return f"调用工具：`{tool_name}`"
        if event_type == "tool_error":
            tool_name = self._truncate_progress_text(payload.get("tool_name") or "unknown")
            return f"工具失败：`{tool_name}`"
        if event_type == "tool_progress":
            tool_name = self._truncate_progress_text(payload.get("tool_name") or "unknown")
            message = self._truncate_progress_text(payload.get("message") or "仍在运行")
            return f"`{tool_name}` {message}"
        if event_type == "workflow_agent_start":
            label = self._truncate_progress_text(
                payload.get("agent_label") or payload.get("agent_id") or "阶段"
            )
            return f"阶段开始：`{label}`"
        if event_type == "workflow_agent_tool_call":
            label = self._truncate_progress_text(
                payload.get("agent_label") or payload.get("agent_id") or "阶段"
            )
            tool_name = self._truncate_progress_text(payload.get("tool") or "unknown")
            return f"`{label}` 调用工具：`{tool_name}`"
        if event_type == "workflow_agent_complete":
            label = self._truncate_progress_text(
                payload.get("agent_label") or payload.get("agent_id") or "阶段"
            )
            return f"阶段完成：`{label}`"
        return None

    @staticmethod
    def _render_progress_text(lines: List[str]) -> str:
        body = "\n".join(f"- {line}" for line in lines[-8:])
        return f"⏳ 正在处理中\n\n{body}" if body else "⏳ 正在处理中..."

    @staticmethod
    def _compose_reasoning_markdown(reasoning_text: str, visible_text: str) -> str:
        """将 reasoning 和正文拼成飞书可渲染的 markdown。"""
        normalized_reasoning = str(reasoning_text or "").strip()
        normalized_visible = str(visible_text or "").strip()

        if not normalized_reasoning:
            return normalized_visible

        sections = [f"**思考过程**\n\n```text\n{normalized_reasoning}\n```"]
        if normalized_visible:
            sections.append(normalized_visible)
        return "\n\n---\n\n".join(sections)

    def _transition_stream_state(
        self,
        state: FeishuStreamState,
        new_phase: FeishuStreamPhase,
        source: str,
        *,
        preserve_terminal_reason: bool = False,
        terminal_reason: Optional[str] = None,
    ) -> None:
        """执行显式状态流转并记录日志。"""
        old_phase = state.phase
        if old_phase == new_phase:
            return
        state.phase = new_phase
        if terminal_reason is not None:
            state.terminal_reason = terminal_reason
        elif not preserve_terminal_reason and new_phase in {
            FeishuStreamPhase.COMPLETED,
            FeishuStreamPhase.ABORTED,
            FeishuStreamPhase.UNAVAILABLE,
            FeishuStreamPhase.FAILED,
        }:
            state.terminal_reason = state.terminal_reason or source
        logger.debug(
            f"[Feishu] Stream phase {state.source_message_id}: "
            f"{old_phase.value} -> {new_phase.value} ({source})"
        )

    def _cleanup_stream_state(self, state: FeishuStreamState) -> None:
        """从运行时索引中移除终态流式回复。"""
        self._stream_states.pop(state.source_message_id, None)
        active = self._active_streams_by_chat.get(state.chat_key)
        if active is state:
            self._active_streams_by_chat.pop(state.chat_key, None)
        self._terminal_stream_ids[state.source_message_id] = None
        while len(self._terminal_stream_ids) > 1000:
            self._terminal_stream_ids.popitem(last=False)

    async def _abort_active_stream_fast(self, chat_key: str, trigger_text: str) -> None:
        """在 /stop 消息进入主处理链前，先结束当前飞书流式卡片。"""
        state = self._active_streams_by_chat.get(chat_key)
        if not state or state.is_terminal:
            return
        logger.info(
            f"[Feishu] Abort fast-path triggered for {chat_key} "
            f"(source={state.source_message_id}, text={trigger_text})"
        )
        await self._abort_stream_state(state, reason="abort_fast_path")

    async def _abort_stream_by_source(self, source_message_id: str, reason: str) -> None:
        """按源消息中止对应流式卡片。"""
        state = self._stream_states.get(source_message_id)
        if not state:
            return
        await self._abort_stream_state(state, reason=reason)

    async def _abort_stream_state(self, state: FeishuStreamState, reason: str) -> None:
        """将当前流式回复终止为 aborted，并尽快落盘到飞书。"""
        if state.is_terminal:
            return

        state.final_requested = True
        self._transition_stream_state(
            state,
            FeishuStreamPhase.ABORTED,
            reason,
            terminal_reason=reason,
        )

        if not state.accumulated_text.strip():
            state.accumulated_text = "已停止生成。"
            state.version += 1

        self._ensure_stream_flush_task(state)
        flush_task = state.flush_task
        if flush_task and not flush_task.done():
            await flush_task

    def _is_stream_unavailable(self, response: Optional[Any] = None, error: Optional[Exception] = None) -> bool:
        """识别消息/卡片已失效，避免对不可用对象持续重试。"""
        text_parts: List[str] = []
        if response is not None:
            text_parts.append(str(getattr(response, "code", "")))
            text_parts.append(str(getattr(response, "msg", "")))
        if error is not None:
            text_parts.append(str(error))
        haystack = " ".join(text_parts).lower()
        return any(hint in haystack for hint in _UNAVAILABLE_HINTS)

    def _mark_stream_unavailable(
        self,
        state: FeishuStreamState,
        source: str,
        *,
        response: Optional[Any] = None,
        error: Optional[Exception] = None,
    ) -> None:
        """标记当前卡片/消息不可用并停止后续更新。"""
        if state.is_terminal:
            return
        self._transition_stream_state(
            state,
            FeishuStreamPhase.UNAVAILABLE,
            source,
            terminal_reason="unavailable",
        )
        logger.warning(
            f"[Feishu] Stream became unavailable: source={source}, "
            f"message_id={state.feishu_message_id}, card_id={state.card_id}, "
            f"error={error}, response_msg={getattr(response, 'msg', '')}"
        )
        self._cleanup_stream_state(state)

    async def _handle_media_message(
        self, msg_type: str, raw_content: str, message_id: str
    ) -> Tuple[str, List[str]]:
        """处理飞书媒体消息，返回 (content, media_files)。"""
        media_files = []
        placeholder = _MSG_TYPE_MAP.get(msg_type, f"[{msg_type}]")
        try:
            payload = json.loads(raw_content) if raw_content else {}
            if not isinstance(payload, dict):
                payload = {}

            file_key = payload.get("image_key") if msg_type == "image" else payload.get("file_key")
            if not file_key:
                return placeholder, media_files

            file_name = payload.get("file_name")
            resource_type = "image" if msg_type == "image" else "file"
            local_path = await self._download_message_resource(
                message_id=message_id,
                file_key=file_key,
                resource_type=resource_type,
                file_name=file_name,
                fallback_image=(msg_type == "image"),
            )
            if not local_path:
                return f"{placeholder}下载失败", media_files

            media_files.append(local_path)
            content = format_inbound_media_text(media_files)
            logger.info(f"Feishu {msg_type} ready: {local_path}")
        except Exception as e:
            logger.error(f"Failed to process {msg_type}: {e}")
            content = f"{placeholder}处理失败"
        return content, media_files

    # ------------------------------------------------------------------
    # 表情回应
    # ------------------------------------------------------------------

    async def _add_reaction(self, message_id: str, emoji_type: str = "THUMBSUP") -> None:
        """添加表情回应到消息（非阻塞）。"""
        if not self._client or not Emoji:
            return

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._add_reaction_sync, message_id, emoji_type)

    def _add_reaction_sync(self, message_id: str, emoji_type: str) -> None:
        """同步添加表情回应（在线程池中运行）。"""
        try:
            request = (
                CreateMessageReactionRequest.builder()
                .message_id(message_id)
                .request_body(
                    CreateMessageReactionRequestBody.builder()
                    .reaction_type(Emoji.builder().emoji_type(emoji_type).build())
                    .build()
                )
                .build()
            )
            response = self._client.im.v1.message_reaction.create(request)
            if not response.success():
                logger.warning(f"Failed to add reaction: code={response.code}, msg={response.msg}")
            else:
                logger.debug(f"Added {emoji_type} reaction to {message_id}")
        except Exception as e:
            logger.warning(f"Error adding reaction: {e}")

    # ------------------------------------------------------------------
    # 图片下载
    # ------------------------------------------------------------------

    async def _download_message_resource(
        self,
        *,
        message_id: str,
        file_key: str,
        resource_type: str,
        file_name: Optional[str] = None,
        fallback_image: bool = False,
    ) -> Optional[str]:
        """下载飞书消息资源并保存到本地。"""
        try:
            from lark_oapi.api.im.v1 import GetMessageResourceRequest

            request = (
                GetMessageResourceRequest.builder()
                .message_id(message_id)
                .file_key(file_key)
                .type(resource_type)
                .build()
            )
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None, lambda: self._client.im.v1.message_resource.get(request)
            )

            if not response.success():
                logger.error(f"Failed to download Feishu resource: {response.msg}")
                if fallback_image:
                    return await self._download_image_fallback(file_key, message_id)
                return None

            data = response.file.read()
            content_type = None
            if hasattr(response, "headers") and isinstance(response.headers, dict):
                content_type = response.headers.get("content-type")

            local_path = save_bytes_to_temp(
                self.name,
                data,
                message_id=message_id,
                filename=file_name or file_key,
                content_type=content_type,
                prefix="feishu_resource",
            )
            logger.info(f"Feishu resource downloaded: {local_path}")
            return local_path
        except Exception as e:
            logger.error(f"Error downloading Feishu resource: {e}")
            if fallback_image:
                return await self._download_image_fallback(file_key, message_id)
            return None

    async def _download_image_fallback(self, image_key: str, message_id: str) -> Optional[str]:
        """备用下载方法：使用 GetImageRequest。"""
        try:
            from lark_oapi.api.im.v1 import GetImageRequest

            logger.info(f"Trying fallback download: {image_key}")
            request = GetImageRequest.builder().image_key(image_key).build()

            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None, lambda: self._client.im.v1.image.get(request)
            )

            if not response.success():
                logger.error(f"Fallback download failed: {response.msg}")
                return None

            local_path = save_bytes_to_temp(
                self.name,
                response.file.read(),
                message_id=message_id,
                filename=f"{image_key}.jpg",
                content_type="image/jpeg",
                prefix="feishu_image",
            )
            logger.info(f"Image downloaded (fallback): {local_path}")
            return local_path
        except Exception as e:
            logger.error(f"Fallback download failed: {e}")
            return None

    # ------------------------------------------------------------------
    # 卡片构建
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_md_table(table_text: str) -> Optional[dict]:
        """解析 markdown 表格为飞书表格元素。"""
        lines = [line.strip() for line in table_text.strip().split("\n") if line.strip()]
        if len(lines) < 3:
            return None

        def _split(line: str) -> List[str]:
            return [c.strip() for c in line.strip("|").split("|")]

        headers = _split(lines[0])
        rows = [_split(line) for line in lines[2:]]
        columns = [
            {"tag": "column", "name": f"c{i}", "display_name": h, "width": "auto"}
            for i, h in enumerate(headers)
        ]
        return {
            "tag": "table",
            "page_size": len(rows) + 1,
            "columns": columns,
            "rows": [
                {f"c{i}": r[i] if i < len(r) else "" for i in range(len(headers))}
                for r in rows
            ],
        }

    def _build_card_elements(self, content: str) -> List[dict]:
        """将内容拆分为 markdown + 表格元素用于飞书卡片。"""
        elements = []
        last_end = 0

        for m in self._TABLE_RE.finditer(content):
            before = content[last_end : m.start()].strip()
            if before:
                elements.append({"tag": "markdown", "content": before})
            elements.append(
                self._parse_md_table(m.group(1))
                or {"tag": "markdown", "content": m.group(1)}
            )
            last_end = m.end()

        remaining = content[last_end:].strip()
        if remaining:
            elements.append({"tag": "markdown", "content": remaining})

        return elements or [{"tag": "markdown", "content": content}]

    # ------------------------------------------------------------------
    # 出站消息发送
    # ------------------------------------------------------------------

    async def send(self, msg: OutboundMessage) -> None:
        """发送消息到飞书。"""
        if not self._client:
            logger.warning("Feishu client not initialized")
            return

        try:
            receive_id_type = "chat_id" if msg.chat_id.startswith("oc_") else "open_id"

            if msg.media:
                await self._send_with_media(msg, receive_id_type)
            else:
                await self._send_card(msg.chat_id, msg.content, receive_id_type)
        except Exception as e:
            logger.error(f"Error sending Feishu message: {e}")

    async def _send_card(self, chat_id: str, content: str, receive_id_type: str) -> None:
        """发送卡片消息（支持 markdown + 表格）"""
        response = await self._run_sync(
            self._create_interactive_message_sync,
            chat_id,
            content,
            receive_id_type,
        )

        if not response.success():
            logger.error(
                f"Failed to send Feishu message: code={response.code}, "
                f"msg={response.msg}, log_id={response.get_log_id()}"
            )
        else:
            logger.debug(f"Feishu message sent to {chat_id}")
    
    async def _send_initial_message(self, chat_id: str, content: str, receive_id_type: str):
        """发送初始消息（用于流式输出）"""
        response = await self._run_sync(
            self._create_interactive_message_sync,
            chat_id,
            content,
            receive_id_type,
        )
        
        if not response.success():
            logger.error(f"Failed to send initial message: {response.msg}")
        
        return response

    async def _create_stream_state(
        self,
        *,
        source_message_id: str,
        chat_key: str,
        chat_id: str,
        receive_id_type: str,
    ) -> Optional[FeishuStreamState]:
        """优先创建 CardKit 流式卡片，失败时回退到普通卡片 patch。"""
        state = FeishuStreamState(
            source_message_id=source_message_id,
            chat_key=chat_key,
            reply_to=chat_id,
            receive_id_type=receive_id_type,
            phase=FeishuStreamPhase.CREATING,
        )
        if FEISHU_CARDKIT_AVAILABLE:
            try:
                card_id = await self._run_sync(self._create_cardkit_card_sync)
                if card_id:
                    response = await self._run_sync(
                        self._send_card_by_card_id_sync,
                        chat_id,
                        card_id,
                        receive_id_type,
                    )
                    if response and response.success():
                        state.mode = "cardkit"
                        state.card_id = card_id
                        state.feishu_message_id = response.data.message_id
                        self._transition_stream_state(state, FeishuStreamPhase.STREAMING, "cardkit_created")
                        await self._set_card_streaming_mode(card_id, True, state)
                        return state
                    logger.warning(
                        "[Feishu] CardKit message create failed, fallback to patch mode: "
                        f"{response.msg if response else 'no response'}"
                    )
            except Exception as e:
                logger.warning(f"[Feishu] CardKit init failed, fallback to patch mode: {e}")

        response = await self._send_initial_message(chat_id, "🤔 思考中...", receive_id_type)
        if response and response.success():
            state.mode = "patch"
            state.feishu_message_id = response.data.message_id
            self._transition_stream_state(state, FeishuStreamPhase.STREAMING, "patch_created")
            return state
        self._transition_stream_state(state, FeishuStreamPhase.FAILED, "create_failed", terminal_reason="create_failed")
        return None

    def _ensure_stream_flush_task(self, state: FeishuStreamState) -> None:
        """确保流式刷新任务存在，并在单任务内追赶后续 chunk。"""
        if state.is_terminal and state.phase == FeishuStreamPhase.UNAVAILABLE:
            return
        flush_task = state.flush_task
        if flush_task and not flush_task.done():
            return
        state.flush_task = asyncio.create_task(self._stream_flush_loop(state))

    async def _stream_flush_loop(self, state: FeishuStreamState) -> None:
        """串行刷新飞书流式内容，避免中途 chunk 被单次 flush 吞掉。"""
        try:
            while True:
                if state.phase == FeishuStreamPhase.UNAVAILABLE:
                    self._cleanup_stream_state(state)
                    return

                is_final = bool(state.final_requested or state.is_terminal)
                flushed_version = int(state.flushed_version)
                current_version = int(state.version)

                if not is_final and current_version <= flushed_version:
                    return

                if not is_final:
                    elapsed = (time.time() * 1000) - float(state.last_update_ms or 0)
                    if elapsed < _STREAM_FLUSH_INTERVAL_MS:
                        await asyncio.sleep((_STREAM_FLUSH_INTERVAL_MS - elapsed) / 1000)

                success = await self._flush_stream_state(state, is_final=is_final)
                if success:
                    state.flushed_version = int(state.version)
                elif not is_final:
                    return

                if is_final:
                    self._cleanup_stream_state(state)
                    return

                if int(state.version) <= int(state.flushed_version) and not state.final_requested:
                    return
        except Exception as e:
            logger.error(f"[Feishu] Stream flush loop error: {e}")
            self._transition_stream_state(
                state,
                FeishuStreamPhase.FAILED,
                "flush_loop_error",
                terminal_reason="flush_loop_error",
            )
            self._cleanup_stream_state(state)

    async def _flush_stream_state(self, state: FeishuStreamState, is_final: bool) -> bool:
        """真正执行一次飞书流式刷新。"""
        async with state.flush_lock:
            rendered_text = state.accumulated_text or ("🤔 思考中..." if not is_final else "✅ 已处理完成。")
            if not is_final and rendered_text == state.last_flushed_text:
                return True

            success = False
            if state.mode == "cardkit" and state.card_id:
                if is_final:
                    success = await self._finalize_streaming_card(
                        state.card_id,
                        rendered_text,
                        state,
                    )
                else:
                    success = await self._stream_card_content(
                        state.card_id,
                        rendered_text,
                        state,
                    )
            elif state.feishu_message_id:
                success = await self._update_message(
                    state.feishu_message_id,
                    rendered_text,
                    state,
                )
            else:
                return False

            if success:
                state.last_update_ms = time.time() * 1000
                state.last_flushed_text = rendered_text
                logger.debug(f"[Feishu] Updated message: {len(rendered_text)} chars")

            return success

    async def _update_message(
        self,
        message_id: str,
        content: str,
        state: Optional[FeishuStreamState] = None,
    ) -> bool:
        """更新消息内容（用于流式输出）"""
        try:
            response = await self._run_sync(self._patch_message_sync, message_id, content)

            if not response.success():
                if state and self._is_stream_unavailable(response=response):
                    self._mark_stream_unavailable(state, "message.patch", response=response)
                    return False
                logger.error(f"Failed to update message: code={response.code}, msg={response.msg}")
                return False

            return True
        except Exception as e:
            if state and self._is_stream_unavailable(error=e):
                self._mark_stream_unavailable(state, "message.patch.exception", error=e)
                return False
            logger.error(f"Error updating message: {e}")
            return False

    async def _stream_card_content(self, card_id: str, content: str, state: FeishuStreamState) -> bool:
        """流式更新 CardKit 卡片正文。"""
        try:
            sequence = int(state.sequence) + 1
            response = await self._run_sync(
                self._stream_card_content_sync,
                card_id,
                content,
                sequence,
            )
            if not response.success():
                if self._is_stream_unavailable(response=response):
                    self._mark_stream_unavailable(state, "cardkit.stream", response=response)
                    return False
                logger.error(f"[Feishu] CardKit content update failed: code={response.code}, msg={response.msg}")
                return False
            state.sequence = sequence
            return True
        except Exception as e:
            if self._is_stream_unavailable(error=e):
                self._mark_stream_unavailable(state, "cardkit.stream.exception", error=e)
                return False
            logger.error(f"[Feishu] CardKit content update error: {e}")
            return False

    async def _set_card_streaming_mode(self, card_id: str, streaming_mode: bool, state: FeishuStreamState) -> bool:
        """切换 CardKit streaming_mode。"""
        try:
            sequence = int(state.sequence) + 1
            response = await self._run_sync(
                self._set_card_streaming_mode_sync,
                card_id,
                streaming_mode,
                sequence,
            )
            if not response.success():
                if self._is_stream_unavailable(response=response):
                    self._mark_stream_unavailable(state, "cardkit.settings", response=response)
                    return False
                logger.warning(f"[Feishu] CardKit settings failed: code={response.code}, msg={response.msg}")
                return False
            state.sequence = sequence
            return True
        except Exception as e:
            if self._is_stream_unavailable(error=e):
                self._mark_stream_unavailable(state, "cardkit.settings.exception", error=e)
                return False
            logger.warning(f"[Feishu] CardKit settings error: {e}")
            return False

    async def _finalize_streaming_card(self, card_id: str, content: str, state: FeishuStreamState) -> bool:
        """结束 CardKit 流式状态并写入最终内容。"""
        try:
            sequence = int(state.sequence) + 1
            response = await self._run_sync(
                self._update_cardkit_card_sync,
                card_id,
                content,
                sequence,
            )
            if not response.success():
                if self._is_stream_unavailable(response=response):
                    self._mark_stream_unavailable(state, "cardkit.final", response=response)
                    return False
                logger.error(f"[Feishu] CardKit final update failed: code={response.code}, msg={response.msg}")
                return False
            state.sequence = sequence
            await self._set_card_streaming_mode(card_id, False, state)
            return True
        except Exception as e:
            if self._is_stream_unavailable(error=e):
                self._mark_stream_unavailable(state, "cardkit.final.exception", error=e)
                return False
            logger.error(f"[Feishu] CardKit final update error: {e}")
            return False

    async def _send_with_media(self, msg: OutboundMessage, receive_id_type: str) -> None:
        """发送带媒体文件的消息。"""
        try:
            if msg.content and msg.content.strip():
                await self._send_card(msg.chat_id, msg.content, receive_id_type)

            for media_path in msg.media:
                await self._send_media_file(msg.chat_id, media_path, receive_id_type)
        except Exception as e:
            logger.error(f"Error sending media: {e}")

    async def _send_media_file(
        self, chat_id: str, file_path: str, receive_id_type: str
    ) -> None:
        """根据文件类型发送图片或文件。"""
        if self._is_image_file(file_path):
            await self._send_image(chat_id, file_path, receive_id_type)
        else:
            await self._send_file(chat_id, file_path, receive_id_type)

    @staticmethod
    def _is_image_file(file_path: str) -> bool:
        """判断是否为图片文件。"""
        return Path(file_path).suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

    async def _run_sync(self, func, *args):
        """在线程池中执行阻塞式飞书 SDK 调用，避免卡住事件循环。"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: func(*args))

    def _create_interactive_message_sync(self, chat_id: str, content: str, receive_id_type: str):
        elements = self._build_card_elements(content)
        card = {"config": {"wide_screen_mode": True}, "elements": elements}
        card_json = json.dumps(card, ensure_ascii=False)

        request = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("interactive")
                .content(card_json)
                .build()
            )
            .build()
        )
        return self._client.im.v1.message.create(request)

    def _patch_message_sync(self, message_id: str, content: str):
        elements = self._build_card_elements(content)
        card = {"config": {"wide_screen_mode": True}, "elements": elements}
        card_json = json.dumps(card, ensure_ascii=False)

        request = (
            PatchMessageRequest.builder()
            .message_id(message_id)
            .request_body(
                PatchMessageRequestBody.builder()
                .content(card_json)
                .build()
            )
            .build()
        )
        return self._client.im.v1.message.patch(request)

    @staticmethod
    def _build_streaming_card(content: str, streaming_mode: bool = True) -> Dict[str, Any]:
        return {
            "schema": "2.0",
            "config": {
                "streaming_mode": streaming_mode,
                "wide_screen_mode": True,
            },
            "body": {
                "elements": [
                    {
                        "tag": "markdown",
                        "content": content or " ",
                        "text_align": "left",
                        "text_size": "normal_v2",
                        "element_id": _STREAMING_ELEMENT_ID,
                    }
                ]
            },
        }

    def _create_cardkit_card_sync(self) -> Optional[str]:
        card_json = json.dumps(self._build_streaming_card(" "), ensure_ascii=False)
        request = (
            CreateCardRequest.builder()
            .request_body(
                CreateCardRequestBody.builder()
                .type("card_json")
                .data(card_json)
                .build()
            )
            .build()
        )
        response = self._client.cardkit.v1.card.create(request)
        if not response.success():
            raise RuntimeError(f"create cardkit card failed: code={response.code}, msg={response.msg}")
        return getattr(response.data, "card_id", None)

    def _send_card_by_card_id_sync(self, chat_id: str, card_id: str, receive_id_type: str):
        content = json.dumps({"type": "card", "data": {"card_id": card_id}}, ensure_ascii=False)
        request = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("interactive")
                .content(content)
                .build()
            )
            .build()
        )
        return self._client.im.v1.message.create(request)

    def _stream_card_content_sync(self, card_id: str, content: str, sequence: int):
        request = (
            ContentCardElementRequest.builder()
            .card_id(card_id)
            .element_id(_STREAMING_ELEMENT_ID)
            .request_body(
                ContentCardElementRequestBody.builder()
                .content(content)
                .sequence(sequence)
                .uuid(str(uuid.uuid4()))
                .build()
            )
            .build()
        )
        return self._client.cardkit.v1.card_element.content(request)

    def _set_card_streaming_mode_sync(self, card_id: str, streaming_mode: bool, sequence: int):
        request = (
            SettingsCardRequest.builder()
            .card_id(card_id)
            .request_body(
                SettingsCardRequestBody.builder()
                .settings(json.dumps({"streaming_mode": streaming_mode}, ensure_ascii=False))
                .sequence(sequence)
                .uuid(str(sequence))
                .build()
            )
            .build()
        )
        return self._client.cardkit.v1.card.settings(request)

    def _update_cardkit_card_sync(self, card_id: str, content: str, sequence: int):
        card = self._build_streaming_card(content, streaming_mode=False)
        request = (
            UpdateCardRequest.builder()
            .card_id(card_id)
            .request_body(
                UpdateCardRequestBody.builder()
                .card(
                    CardKitCard.builder()
                    .type("card_json")
                    .data(json.dumps(card, ensure_ascii=False))
                    .build()
                )
                .sequence(sequence)
                .uuid(str(sequence))
                .build()
            )
            .build()
        )
        return self._client.cardkit.v1.card.update(request)

    async def _send_image(
        self, chat_id: str, image_path: str, receive_id_type: str
    ) -> None:
        """上传并发送图片。"""
        try:
            image_file = Path(image_path)
            if not image_file.exists():
                logger.error(f"Image not found: {image_path}")
                return

            upload_response = await self._run_sync(self._upload_image_sync, image_file)

            if not upload_response.success():
                logger.error(f"Failed to upload image: {upload_response.msg}")
                return

            image_key = upload_response.data.image_key
            logger.info(f"Image uploaded: {image_key}")

            content = json.dumps({"image_key": image_key})
            request = (
                CreateMessageRequest.builder()
                .receive_id_type(receive_id_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("image")
                    .content(content)
                    .build()
                )
                .build()
            )
            response = await self._run_sync(
                lambda req: self._client.im.v1.message.create(req),
                request,
            )

            if not response.success():
                logger.error(f"Failed to send image: {response.msg}")
            else:
                logger.info(f"Image sent to {chat_id}")
        except Exception as e:
            logger.error(f"Error sending image: {e}")

    async def _send_file(
        self, chat_id: str, file_path: str, receive_id_type: str
    ) -> None:
        """上传并发送文件。"""
        try:
            file = Path(file_path)
            if not file.exists():
                logger.error(f"File not found: {file_path}")
                return

            from lark_oapi.api.im.v1 import CreateFileRequest, CreateFileRequestBody

            upload_response = await self._run_sync(self._upload_file_sync, file)

            if not upload_response.success():
                logger.error(f"Failed to upload file: {upload_response.msg}")
                return

            file_key = upload_response.data.file_key
            logger.info(f"File uploaded: {file_key}")

            content = json.dumps({"file_key": file_key})
            request = (
                CreateMessageRequest.builder()
                .receive_id_type(receive_id_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("file")
                    .content(content)
                    .build()
                )
                .build()
            )
            response = await self._run_sync(
                lambda req: self._client.im.v1.message.create(req),
                request,
            )

            if not response.success():
                logger.error(f"Failed to send file: {response.msg}")
            else:
                logger.info(f"File sent to {chat_id}")
        except Exception as e:
            logger.error(f"Error sending file: {e}")

    def _upload_image_sync(self, image_file: Path):
        with image_file.open("rb") as image_handle:
            upload_request = (
                CreateImageRequest.builder()
                .request_body(
                    CreateImageRequestBody.builder()
                    .image_type("message")
                    .image(image_handle)
                    .build()
                )
                .build()
            )
            return self._client.im.v1.image.create(upload_request)

    def _upload_file_sync(self, file: Path):
        from lark_oapi.api.im.v1 import CreateFileRequest, CreateFileRequestBody

        with file.open("rb") as file_handle:
            upload_request = (
                CreateFileRequest.builder()
                .request_body(
                    CreateFileRequestBody.builder()
                    .file_type("stream")
                    .file_name(file.name)
                    .file(file_handle)
                    .build()
                )
                .build()
            )
            return self._client.im.v1.file.create(upload_request)

    # ------------------------------------------------------------------
    # 连接测试
    # ------------------------------------------------------------------

    async def test_connection(self) -> Dict[str, Any]:
        """测试飞书连接（获取 tenant_access_token 验证凭据）。"""
        if not self.config.app_id or not self.config.app_secret:
            return {"success": False, "message": "App ID or App Secret not configured"}

        if not FEISHU_AVAILABLE:
            return {"success": False, "message": "Feishu SDK not installed"}

        if not self.config.app_id.startswith("cli_"):
            return {"success": False, "message": "Invalid App ID format (should start with 'cli_')"}
        if len(self.config.app_id) < 12:
            return {"success": False, "message": "Invalid App ID format (too short)"}
        if len(self.config.app_secret) < 24:
            return {"success": False, "message": "Invalid App Secret format (too short)"}

        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as http_client:
                response = await http_client.post(
                    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                    json={
                        "app_id": self.config.app_id,
                        "app_secret": self.config.app_secret,
                    },
                )
                result = response.json()

                if result.get("code") == 0:
                    return {
                        "success": True,
                        "message": "Feishu credentials verified",
                        "bot_info": {
                            "app_id": self.config.app_id[:12] + "...",
                            "status": "credentials_verified",
                        },
                    }

                error_msg = result.get("msg", "Unknown error")
                error_code = result.get("code", "")
                if "99991663" in str(error_code) or "app_id" in error_msg.lower():
                    return {"success": False, "message": "Invalid App ID or App Secret"}
                return {"success": False, "message": f"Authentication failed: {error_msg}"}

        except asyncio.TimeoutError:
            return {"success": False, "message": "Connection timeout"}
        except Exception as e:
            error_msg = str(e)
            if any(k in error_msg.lower() for k in ("app_id", "app_secret", "99991663")):
                return {"success": False, "message": "Invalid App ID or App Secret"}
            return {"success": False, "message": f"Connection test failed: {error_msg}"}

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def display_name(self) -> str:
        return "Feishu"
