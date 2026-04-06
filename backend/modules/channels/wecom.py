"""企业微信频道模块

基于 WebSocket 长连接的企业微信机器人实现。
支持流式回复和实时消息处理。
"""

import asyncio
import base64
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Dict, List, Callable
import threading
import re

import httpx
from loguru import logger

from backend.modules.channels.base import BaseChannel, InboundMessage, OutboundMessage
from backend.modules.channels.media_utils import (
    decrypt_wecom_media_bytes,
    extract_filename_from_content_disposition,
    format_inbound_media_text,
    save_bytes_to_temp,
)

try:
    import websockets
    import websockets.protocol
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    websockets = None

# 长连接命令常量
class LongConnCmd:
    SUBSCRIBE = "aibot_subscribe"
    PING = "ping"
    MSG_CALLBACK = "aibot_msg_callback"
    EVENT_CALLBACK = "aibot_event_callback"
    RESPOND_WELCOME_MSG = "aibot_respond_welcome_msg"
    RESPOND_MSG = "aibot_respond_msg"
    RESPOND_UPDATE_MSG = "aibot_respond_update_msg"
    SEND_MSG = "aibot_send_msg"

# 长连接错误类
class LongConnError(Exception):
    """长连接基础错误"""
    pass

class LongConnPermanentError(LongConnError):
    """不可恢复的长连接错误（如认证失败）"""
    pass

class LongConnAPIError(LongConnError):
    """企业微信 API 返回的业务错误"""
    def __init__(self, cmd: str, request_id: str, err_code: int, err_msg: str):
        self.cmd = cmd
        self.request_id = request_id
        self.err_code = err_code
        self.err_msg = err_msg
        super().__init__(f"longconn api error: cmd={cmd} req_id={request_id} errcode={err_code} errmsg={err_msg}")

@dataclass
class StreamState:
    """流式回复状态管理"""
    stream_id: str
    accumulated_text: str = ""
    reasoning_text: str = ""
    progress_lines: List[str] = field(default_factory=list)
    last_send_time: float = 0
    message_count: int = 0
    finished: bool = False
    request_id: str = ""

@dataclass
class LongConnRequest:
    """长连接请求帧"""
    cmd: str
    headers: Dict[str, str]
    body: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "cmd": self.cmd,
            "headers": self.headers
        }
        if self.body is not None:
            result["body"] = self.body
        return result

@dataclass
class LongConnResponse:
    """长连接响应帧"""
    headers: Dict[str, str]
    err_code: int = 0
    err_msg: str = ""

@dataclass
class LongConnFrame:
    """长连接原始帧"""
    cmd: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    body: Optional[Dict[str, Any]] = None
    err_code: Optional[int] = None
    err_msg: Optional[str] = None
    
    def has_ack_result(self) -> bool:
        """判断是否是命令响应帧"""
        return self.err_code is not None or self.err_msg
    
    def is_callback(self) -> bool:
        """判断是否是回调帧"""
        return (self.cmd in [LongConnCmd.MSG_CALLBACK, LongConnCmd.EVENT_CALLBACK] 
                and self.body is not None)

def normalize_thinking_tags(text: str) -> str:
    """标准化思考标签"""
    if not text:
        return ""
    
    # 处理 <think> 标签
    text = re.sub(r'<think>(.*?)</think>', r'\1', text, flags=re.DOTALL)
    return text.strip()

def build_stream_content(reasoning_text: str = "", visible_text: str = "", finish: bool = False) -> str:
    """构建流式内容"""
    normalized_reasoning = str(reasoning_text or "").strip()
    normalized_visible = str(visible_text or "").strip()
    
    if not normalized_reasoning:
        return normalized_visible
    
    should_close_think = finish or bool(normalized_visible)
    think_block = f"<think>{normalized_reasoning}</think>" if should_close_think else f"<think>{normalized_reasoning}"
    
    return f"{think_block}\n{normalized_visible}" if normalized_visible else think_block


_THINK_TAG_RE = re.compile(r"<\s*(/?)\s*(?:think(?:ing)?|thought)\b[^<>]*>", re.IGNORECASE)
_FAST_COMMAND_EXACT = {
    "/new",
    "/newsession",
    "/new_session",
    "/n",
    "/list",
    "/sessions",
    "/list_sessions",
    "/l",
    "/ls",
    "/all",
    "/all_sessions",
    "/al",
    "/clear",
    "/clear_history",
    "/c",
    "/stop",
    "/cancel",
    "/help",
    "/h",
    "/?",
    "/provider",
    "/m",
    "/personality",
    "/p",
    "/team",
}
_FAST_COMMAND_PREFIXES = (
    "/switch ",
    "/s ",
    "/route",
    "/rt",
    "/coder",
    "/cdr",
    "/provider ",
    "/m ",
    "/personality ",
    "/p ",
)


def normalize_thinking_tags(text: str) -> str:
    """Normalize think tag variants to the canonical WeCom form."""
    if not text:
        return ""

    normalized = _THINK_TAG_RE.sub(
        lambda match: "</think>" if match.group(1) else "<think>",
        str(text),
    )
    return normalized.strip()


def is_fast_command_text(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    if normalized in _FAST_COMMAND_EXACT:
        return True
    return normalized.startswith(_FAST_COMMAND_PREFIXES)


def truncate_progress_text(value: Any, limit: int = 80) -> str:
    text = str(value or "").strip().replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def build_tool_progress_line(event_type: str, payload: Dict[str, Any]) -> Optional[str]:
    if event_type == "tool_call":
        tool_name = truncate_progress_text(payload.get("tool_name") or "unknown")
        return f"调用工具：`{tool_name}`"
    if event_type == "tool_result":
        tool_name = truncate_progress_text(payload.get("tool_name") or "unknown")
        return f"工具完成：`{tool_name}`"
    if event_type == "tool_error":
        tool_name = truncate_progress_text(payload.get("tool_name") or "unknown")
        return f"工具失败：`{tool_name}`"
    if event_type == "tool_progress":
        tool_name = truncate_progress_text(payload.get("tool_name") or "unknown")
        message = truncate_progress_text(payload.get("message") or "仍在运行")
        return f"`{tool_name}` {message}"
    if event_type == "workflow_agent_start":
        label = truncate_progress_text(
            payload.get("agent_label") or payload.get("agent_id") or "阶段"
        )
        return f"阶段开始：`{label}`"
    if event_type == "workflow_agent_tool_call":
        label = truncate_progress_text(
            payload.get("agent_label") or payload.get("agent_id") or "阶段"
        )
        tool_name = truncate_progress_text(payload.get("tool") or "unknown")
        return f"`{label}` 调用工具：`{tool_name}`"
    if event_type == "workflow_agent_complete":
        label = truncate_progress_text(
            payload.get("agent_label") or payload.get("agent_id") or "阶段"
        )
        return f"阶段完成：`{label}`"
    return None


def render_progress_text(lines: List[str]) -> str:
    body = "\n".join(f"- {line}" for line in lines[-8:])
    return f"处理中...\n\n{body}" if body else ""


def resolve_stream_visible_text(state: StreamState, *, include_progress: bool) -> str:
    visible_text = str(state.accumulated_text or "").strip()
    if visible_text:
        return visible_text
    if include_progress:
        return render_progress_text(state.progress_lines)
    return ""


MAX_REPLY_MSG_ITEMS = 10
MAX_REPLY_IMAGE_BYTES = 10 * 1024 * 1024
SUPPORTED_REPLY_IMAGE_SIGNATURES = {
    "png": bytes.fromhex("89504e470d0a1a0a"),
    "jpg": bytes.fromhex("ffd8ff"),
}
REPLY_MEDIA_DIRECTIVE_PATTERN = re.compile(
    r"^\s*(?:[-*•]\s+|\d+\.\s+)?MEDIA\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)


class LongConnBot:
    """企业微信长连接机器人"""
    
    def __init__(self, bot_id: str, secret: str, handler: Optional[Callable] = None, 
                 websocket_url: str = "wss://openws.work.weixin.qq.com"):
        if not bot_id:
            raise ValueError("bot_id is required")
        if not secret:
            raise ValueError("secret is required")
            
        self.bot_id = bot_id
        self.secret = secret
        self.handler = handler
        
        # 连接配置
        self.ws_url = websocket_url
        self.ping_interval = 30  # 秒
        self.reconnect_interval = 3  # 秒
        self.request_timeout = 10  # 秒
        self.write_timeout = 5  # 秒
        
        # 流式回复配置
        self.stream_throttle_ms = 800  # 流式更新节流间隔（毫秒）
        self.max_intermediate_messages = 85  # 最大中间消息数
        self.thinking_message = "思考中..."  # 思考提示消息
        
        # 连接状态
        self.conn_lock = threading.RLock()
        self.conn: Optional[websockets.WebSocketClientProtocol] = None
        self.write_lock = asyncio.Lock()
        
        # 请求管理
        self.pending_lock = threading.Lock()
        self.pending: Dict[str, asyncio.Future] = {}
        
        # 流式状态管理
        self.stream_states: Dict[str, StreamState] = {}  # message_id -> StreamState
        self.stream_lock = threading.Lock()
        
        # 控制标志
        self.close_once = threading.Lock()
        self.closed_event = asyncio.Event()
        self.running = False
    
    def generate_request_id(self) -> str:
        """生成请求ID"""
        return f"req_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    
    def set_stream_state(self, message_id: str, state: StreamState) -> None:
        """设置流式状态"""
        with self.stream_lock:
            self.stream_states[message_id] = state
    
    def get_stream_state(self, message_id: str) -> Optional[StreamState]:
        """获取流式状态"""
        with self.stream_lock:
            return self.stream_states.get(message_id)
    
    def delete_stream_state(self, message_id: str) -> None:
        """删除流式状态"""
        with self.stream_lock:
            self.stream_states.pop(message_id, None)
    def can_send_intermediate(self, state: StreamState) -> bool:
        """检查是否可以发送中间消息"""
        return state.message_count < self.max_intermediate_messages
    
    def should_throttle_update(self, state: StreamState) -> bool:
        """检查是否应该节流更新"""
        elapsed = (time.time() * 1000) - state.last_send_time
        return elapsed < self.stream_throttle_ms
    
    async def send_stream_reply(
        self,
        frame: LongConnFrame,
        stream_id: str,
        text: str,
        finish: bool = False,
        msg_items: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """发送流式回复"""
        normalized_text = normalize_thinking_tags(text)
        if not normalized_text and not finish and not msg_items:
            return
        
        conn = self._current_conn()
        if not conn:
            raise LongConnError("WebSocket not connected")
        
        # 基于官方 SDK 的流式回复格式
        reply_body = {
            "msgtype": "stream",
            "stream": {
                "id": stream_id,
                "finish": finish,
                "content": normalized_text
            }
        }
        if msg_items:
            reply_body["stream"]["msg_item"] = msg_items
        
        request = LongConnRequest(
            cmd=LongConnCmd.RESPOND_MSG,
            headers={"req_id": frame.headers.get("req_id", "")},
            body=reply_body
        )
        
        req_id = frame.headers.get("req_id", "")
        wait_for_ack = finish or bool(msg_items)

        if wait_for_ack and req_id:
            response = await self._send_request_and_wait(
                LongConnCmd.RESPOND_MSG,
                req_id,
                reply_body,
            )
            logger.info(
                f"[LongConnBot] Stream reply acked finish={finish} "
                f"msg_items={len(msg_items or [])} err_code={response.err_code} err_msg={response.err_msg}"
            )
        else:
            await self._write_json(conn, request.to_dict())
            logger.debug(
                f"[LongConnBot] → Stream reply sent cmd={request.cmd} finish={finish} "
                f"msg_items={len(msg_items or [])}: {normalized_text[:50]}..."
            )
    
    async def send_thinking_reply(self, frame: LongConnFrame, stream_id: str) -> None:
        """发送思考提示"""
        try:
            await self.send_stream_reply(frame, stream_id, self.thinking_message, finish=False)
        except Exception as e:
            logger.error(f"[LongConnBot] Failed to send thinking reply: {e}")

    @staticmethod
    def _detect_reply_image_format(image_bytes: bytes) -> Optional[str]:
        """检测企业微信被动回复支持的图片格式。"""
        if image_bytes.startswith(SUPPORTED_REPLY_IMAGE_SIGNATURES["png"]):
            return "png"
        if image_bytes.startswith(SUPPORTED_REPLY_IMAGE_SIGNATURES["jpg"]):
            return "jpg"
        return None

    @staticmethod
    def _split_reply_media_from_text(text: str) -> tuple[str, List[str]]:
        """从最终回复文本中提取 MEDIA:/abs/path 指令。"""
        if not text:
            return "", []

        media_paths: List[str] = []
        kept_lines: List[str] = []
        for line in text.splitlines():
            match = REPLY_MEDIA_DIRECTIVE_PATTERN.match(line)
            if not match:
                kept_lines.append(line)
                continue

            media_path = match.group(1).strip().strip("`").strip()
            if media_path:
                media_paths.append(media_path)

        cleaned_text = "\n".join(kept_lines)
        cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text).strip()
        return cleaned_text, media_paths

    def _build_reply_image_msg_items(self, media_paths: List[str]) -> List[Dict[str, Any]]:
        """构建企业微信长连接最终帧图片 msg_item。"""
        msg_items: List[Dict[str, Any]] = []
        seen: set[str] = set()

        for media_path in media_paths:
            normalized_path = str(media_path).strip()
            if not normalized_path or normalized_path in seen:
                continue
            seen.add(normalized_path)

            if len(msg_items) >= MAX_REPLY_MSG_ITEMS:
                logger.warning(
                    f"[LongConnBot] Reply image count exceeds {MAX_REPLY_MSG_ITEMS}, remaining images skipped"
                )
                break

            path = Path(normalized_path)
            if not path.is_file():
                logger.warning(f"[LongConnBot] Reply image not found: {normalized_path}")
                continue

            image_bytes = path.read_bytes()
            if len(image_bytes) > MAX_REPLY_IMAGE_BYTES:
                logger.warning(f"[LongConnBot] Reply image too large ({len(image_bytes)} bytes): {normalized_path}")
                continue

            image_format = self._detect_reply_image_format(image_bytes)
            if not image_format:
                logger.warning(
                    f"[LongConnBot] Reply media format is not supported by WeCom passive reply: {normalized_path}"
                )
                continue

            md5_value = hashlib.md5(image_bytes).hexdigest()
            logger.info(
                f"[LongConnBot] Reply image prepared path={normalized_path} format={image_format} "
                f"bytes={len(image_bytes)} md5={md5_value}"
            )
            msg_items.append(
                {
                    "msgtype": "image",
                    "image": {
                        "base64": base64.b64encode(image_bytes).decode("utf-8"),
                        "md5": md5_value,
                    },
                }
            )

        return msg_items

    def prepare_reply_payload(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, List[Dict[str, Any]]]:
        metadata = metadata or {}
        content_to_send, directive_media_paths = self._split_reply_media_from_text(text)
        pending_media_paths = metadata.get("_wecom_pending_media_paths", []) or []
        pending_media_text = str(metadata.get("_wecom_pending_media_text", "") or "").strip()

        reply_media_paths = [*pending_media_paths, *directive_media_paths]
        msg_items = self._build_reply_image_msg_items(reply_media_paths)

        if pending_media_text and not content_to_send:
            content_to_send = pending_media_text
        elif not content_to_send and msg_items:
            content_to_send = "已发送图片，请查看。"

        return content_to_send, msg_items

    async def start(self, ctx: Optional[asyncio.Event] = None) -> None:
        """启动长连接机器人"""
        if self.running:
            return
            
        self.running = True
        logger.info(f"[LongConnBot] Starting bot {self.bot_id[:12]}...")
        
        try:
            while self.running and not self.closed_event.is_set():
                # 检查上下文取消
                if ctx and ctx.is_set():
                    break
                
                try:
                    await self._run_session(ctx)
                    break  # 正常退出
                except LongConnPermanentError as e:
                    logger.error(f"[LongConnBot] Permanent error: {e}")
                    raise e
                except Exception as e:
                    logger.warning(f"[LongConnBot] Session error: {e}, reconnecting in {self.reconnect_interval}s...")
                    
                    # 等待重连间隔
                    try:
                        await asyncio.wait_for(self.closed_event.wait(), timeout=self.reconnect_interval)
                        break  # 被主动关闭
                    except asyncio.TimeoutError:
                        continue  # 继续重连
                        
        finally:
            self.running = False
            await self._cleanup()
    async def _run_session(self, ctx: Optional[asyncio.Event] = None) -> None:
        """运行一次完整的长连接会话"""
        # 建立 WebSocket 连接
        conn = await websockets.connect(
            self.ws_url,
            ping_interval=None,  # 使用自定义心跳
            close_timeout=10
        )
        read_task: Optional[asyncio.Task] = None
        ping_task: Optional[asyncio.Task] = None
        
        try:
            # 设置当前连接
            self._set_conn(conn)
            logger.info(f"[LongConnBot] WebSocket connected")
            
            # 启动读循环
            read_task = asyncio.create_task(self._read_loop(conn))
            
            # 发送订阅命令
            await self._subscribe()
            logger.success(f"[LongConnBot] Subscribed successfully")
            
            # 启动心跳循环
            ping_task = asyncio.create_task(self._ping_loop(ctx))
            
            # 等待任一任务完成
            done, pending = await asyncio.wait(
                [read_task, ping_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # 取消未完成的任务
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            # 检查是否有异常
            for task in done:
                if task.exception():
                    raise task.exception()
                    
        finally:
            for task in (ping_task, read_task):
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, websockets.exceptions.ConnectionClosed, websockets.exceptions.ConnectionClosedError):
                        pass
                    except Exception as e:
                        logger.debug(f"[LongConnBot] Background task cleanup error: {e}")
            self._release_conn(conn, Exception("session closed"))
    
    async def _subscribe(self) -> None:
        """发送订阅命令"""
        request_id = self.generate_request_id()
        body = {
            "bot_id": self.bot_id,
            "secret": self.secret
        }
        
        await self._send_request_and_wait(LongConnCmd.SUBSCRIBE, request_id, body)
    
    async def _read_loop(self, conn: websockets.WebSocketClientProtocol) -> None:
        """读取消息循环"""
        try:
            async for message in conn:
                await self._handle_raw_message(message)
        except websockets.exceptions.ConnectionClosed as e:
            if self.running and not self.closed_event.is_set():
                logger.info(f"[LongConnBot] WebSocket closed: {e.code} {e.reason}")
            else:
                logger.debug(f"[LongConnBot] WebSocket closed during shutdown: {e.code}")
            raise
        except asyncio.CancelledError:
            logger.debug("[LongConnBot] Read loop cancelled")
            raise
        except Exception as e:
            if self.running:
                logger.error(f"[LongConnBot] Read loop error: {e}")
            else:
                logger.debug(f"[LongConnBot] Read loop error during shutdown: {e}")
            raise
    
    async def _ping_loop(self, ctx: Optional[asyncio.Event] = None) -> None:
        """心跳循环"""
        try:
            while self.running and not self.closed_event.is_set():
                # 检查上下文取消
                if ctx and ctx.is_set():
                    break
                
                try:
                    await asyncio.sleep(self.ping_interval)
                except asyncio.CancelledError:
                    logger.debug("[LongConnBot] Ping loop cancelled during sleep")
                    break
                
                # 再次检查状态
                if not self.running or self.closed_event.is_set():
                    break
                
                # 发送心跳
                try:
                    request_id = self.generate_request_id()
                    await self._send_request_and_wait(LongConnCmd.PING, request_id, None)
                    logger.debug(f"[LongConnBot] Ping sent")
                except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
                    logger.debug("[LongConnBot] Ping failed, connection closed")
                    break
                except Exception as e:
                    if self.running:
                        logger.warning(f"[LongConnBot] Ping failed: {e}")
                    break
                
        except asyncio.CancelledError:
            logger.debug("[LongConnBot] Ping loop cancelled")
        except Exception as e:
            if self.running and not self.closed_event.is_set():
                logger.error(f"[LongConnBot] Ping loop error: {e}")
            else:
                logger.debug(f"[LongConnBot] Ping loop error during shutdown: {e}")
    async def _handle_raw_message(self, raw_message: str) -> None:
        """处理原始消息"""
        try:
            data = json.loads(raw_message)
            frame = LongConnFrame(
                cmd=data.get("cmd"),
                headers=data.get("headers", {}),
                body=data.get("body"),
                err_code=data.get("errcode"),
                err_msg=data.get("errmsg", "")
            )
            
            logger.debug(f"[LongConnBot] Received frame: cmd={frame.cmd}")
            
            # 处理命令响应
            if frame.has_ack_result():
                request_id = frame.headers.get("req_id", "")
                if request_id and self._complete_pending(request_id, frame):
                    return
            
            # 处理回调消息
            if frame.is_callback():
                await self._handle_callback(frame)
                
        except json.JSONDecodeError as e:
            logger.warning(f"[LongConnBot] Failed to parse message: {e}")
        except Exception as e:
            logger.error(f"[LongConnBot] Error handling message: {e}")
    
    async def _handle_callback(self, frame: LongConnFrame) -> None:
        """处理回调消息"""
        if not self.handler:
            return
            
        try:
            # 根据回调类型处理
            if frame.cmd == LongConnCmd.MSG_CALLBACK:
                await self._handle_message_callback(frame)
            elif frame.cmd == LongConnCmd.EVENT_CALLBACK:
                await self._handle_event_callback(frame)
        except Exception as e:
            logger.error(f"[LongConnBot] Callback handler error: {e}")
    
    async def _handle_message_callback(self, frame: LongConnFrame) -> None:
        """处理消息回调"""
        if not frame.body:
            return
            
        # 提取消息信息
        sender_info = frame.body.get("from", {}) or {}
        sender_id = sender_info.get("userid", "")
        sender_name = sender_info.get("name") or sender_id
        chat_id = frame.body.get("chatid", sender_id)
        msg_type = frame.body.get("msgtype", "")
        message_id = frame.body.get("msgid", "")
        
        # 解析消息内容
        content = ""
        if msg_type == "text":
            content = frame.body.get("text", {}).get("content", "")
        elif msg_type == "voice":
            content = frame.body.get("voice", {}).get("content", "")
        elif msg_type == "mixed":
            # 图文混排
            text_parts = []
            msg_items = frame.body.get("mixed", {}).get("msg_item", [])
            for item in msg_items:
                if item.get("msgtype") == "text":
                    text_parts.append(item.get("text", {}).get("content", ""))
            content = "\n".join(text_parts)
        
        if not content and msg_type not in {"image", "file", "mixed"}:
            return

        preview = content or f"[{msg_type}]"
        logger.info(f"[LongConnBot] ← Message from {sender_id}: {preview[:50]}...")
        
        # 初始化流式状态
        stream_id = self.generate_request_id()
        request_id = frame.headers.get("req_id", "")
        
        stream_state = StreamState(
            stream_id=stream_id,
            request_id=request_id
        )
        self.set_stream_state(message_id, stream_state)
        metadata = frame.body.copy()
        metadata["sender_name"] = sender_name
        metadata["_wecom_stream_message_id"] = message_id
        metadata["_wecom_frame_headers"] = dict(frame.headers or {})
        
        # 发送思考提示
        if not is_fast_command_text(content):
            await self.send_thinking_reply(frame, stream_id)
        
        if self.handler:
            try:
                async def push_progress_line(line: str) -> None:
                    if not line:
                        return

                    state = self.get_stream_state(message_id)
                    if not state or state.finished:
                        return

                    if state.progress_lines and state.progress_lines[-1] == line:
                        return

                    state.progress_lines.append(line)
                    if len(state.progress_lines) > 8:
                        state.progress_lines = state.progress_lines[-8:]

                    if state.accumulated_text.strip():
                        return

                    if not self.can_send_intermediate(state):
                        return

                    if self.should_throttle_update(state):
                        return

                    content_to_send = build_stream_content(
                        reasoning_text=state.reasoning_text,
                        visible_text=resolve_stream_visible_text(state, include_progress=True),
                        finish=False,
                    )
                    await self.send_stream_reply(
                        frame,
                        state.stream_id,
                        content_to_send,
                        finish=False,
                    )
                    state.last_send_time = time.time() * 1000
                    state.message_count += 1

                async def tool_event_handler(event_type: str, payload: Dict[str, Any]) -> None:
                    line = build_tool_progress_line(event_type, payload or {})
                    if line:
                        await push_progress_line(line)

                async def abort_stream_handler() -> None:
                    state = self.get_stream_state(message_id)
                    if not state or state.finished:
                        return
                    state.finished = True
                    await self.send_stream_reply(
                        frame,
                        state.stream_id,
                        "已停止生成。",
                        finish=True,
                    )
                    self.delete_stream_state(message_id)

                async def stream_handler(text_chunk: str, is_final: bool = False, is_reasoning: bool = False):
                    """流式处理器：累积文本并发送到企业微信"""
                    state = self.get_stream_state(message_id)
                    if not state:
                        logger.warning(f"[LongConnBot] Stream state not found for message {message_id}")
                        return
                    
                    # 累积文本
                    if is_reasoning:
                        state.reasoning_text += text_chunk
                    else:
                        state.accumulated_text += text_chunk
                    
                    logger.debug(f"[LongConnBot] Stream: chunk={len(text_chunk)}, final={is_final}, total={len(state.accumulated_text)}")
                    
                    # 最终消息：发送完整内容
                    if is_final:
                        content_to_send = build_stream_content(
                            reasoning_text=state.reasoning_text,
                            visible_text=resolve_stream_visible_text(state, include_progress=False),
                            finish=True
                        )
                        content_to_send, msg_items = self.prepare_reply_payload(content_to_send, metadata)
                        if not content_to_send and state.progress_lines and not msg_items:
                            content_to_send = "处理完成。"

                        logger.info(
                            f"[LongConnBot] Final reply: {len(content_to_send)} chars, "
                            f"reply_images={len(msg_items)}"
                        )
                        await self.send_stream_reply(
                            frame,
                            state.stream_id,
                            content_to_send,
                            finish=True,
                            msg_items=msg_items or None,
                        )
                        
                        state.finished = True
                        self.delete_stream_state(message_id)
                        return
                    
                    # 中间更新：检查节流
                    if not self.can_send_intermediate(state):
                        return
                    
                    if self.should_throttle_update(state):
                        return
                    
                    # 发送中间更新
                    content_to_send = build_stream_content(
                        reasoning_text=state.reasoning_text,
                        visible_text=resolve_stream_visible_text(state, include_progress=True),
                        finish=False
                    )
                    
                    await self.send_stream_reply(
                        frame,
                        state.stream_id,
                        content_to_send,
                        finish=False,
                    )
                    state.last_send_time = time.time() * 1000
                    state.message_count += 1
                
                # 通过 metadata 传递流式处理器
                metadata['_stream_handler'] = stream_handler
                metadata["_tool_event_handler"] = tool_event_handler
                metadata["_stream_abort_handler"] = abort_stream_handler
                
                await self.handler(sender_id, chat_id, content, metadata)
                
            except Exception as e:
                logger.error(f"[LongConnBot] Handler error: {e}")
                state = self.get_stream_state(message_id)
                if state:
                    await self.send_stream_reply(
                        frame,
                        state.stream_id,
                        "处理消息时发生错误，请稍后重试。",
                        finish=True,
                    )
                    self.delete_stream_state(message_id)
    async def _handle_event_callback(self, frame: LongConnFrame) -> None:
        """处理事件回调"""
        if not frame.body:
            return
            
        event_type = frame.body.get("event", {}).get("event_type", "")
        logger.info(f"[LongConnBot] Event: {event_type}")
        
        # 处理进入聊天事件
        if event_type == "enter_chat":
            welcome_msg = {
                "msgtype": "text",
                "text": {"content": "你好,我是 AI 助手。"}
            }
            await self._send_callback_command(LongConnCmd.RESPOND_WELCOME_MSG, frame.headers.get("req_id", ""), welcome_msg)
    
    async def _send_callback_command(self, command: str, request_id: str, body: Any) -> None:
        """发送回调命令 - 不等待响应避免超时"""
        try:
            conn = self._current_conn()
            if not conn:
                raise LongConnError("WebSocket not connected")
            
            request = LongConnRequest(
                cmd=command,
                headers={"req_id": request_id},
                body=body
            )
            
            await self._write_json(conn, request.to_dict())
            logger.debug(f"[LongConnBot] → Callback command sent: {command}")
            
        except Exception as e:
            logger.error(f"[LongConnBot] Failed to send callback command {command}: {e}")
            raise
    
    async def _send_request_and_wait(self, command: str, request_id: str, body: Any) -> LongConnResponse:
        """发送请求并等待响应"""
        if not request_id:
            raise ValueError("request_id is required")
            
        conn = self._current_conn()
        if not conn:
            raise LongConnError("WebSocket not connected")
        
        # 注册等待器
        future = asyncio.Future()
        with self.pending_lock:
            self.pending[request_id] = future
        
        try:
            # 发送请求
            request = LongConnRequest(
                cmd=command,
                headers={"req_id": request_id},
                body=body
            )
            
            await self._write_json(conn, request.to_dict())
            
            # 等待响应
            try:
                frame = await asyncio.wait_for(future, timeout=self.request_timeout)
                
                # 检查错误
                if frame.err_code and frame.err_code != 0:
                    if command == LongConnCmd.SUBSCRIBE and frame.err_code in [40001, 40014, 93019]:
                        # 认证失败，永久错误
                        raise LongConnPermanentError(f"Authentication failed: {frame.err_code} {frame.err_msg}")
                    else:
                        raise LongConnAPIError(command, request_id, frame.err_code, frame.err_msg)
                
                return LongConnResponse(
                    headers=frame.headers or {},
                    err_code=frame.err_code or 0,
                    err_msg=frame.err_msg or ""
                )
                
            except asyncio.TimeoutError:
                raise LongConnError(f"Request timeout: {command}")
                
        finally:
            # 清理等待器
            with self.pending_lock:
                self.pending.pop(request_id, None)
    async def _write_json(self, conn: websockets.WebSocketClientProtocol, payload: Any) -> None:
        """线程安全地写入 JSON"""
        if not conn:
            raise LongConnError("WebSocket connection is None")
        
        async with self.write_lock:
            try:
                await asyncio.wait_for(conn.send(json.dumps(payload)), timeout=self.write_timeout)
            except asyncio.TimeoutError:
                raise LongConnError("Write timeout")
    
    def _complete_pending(self, request_id: str, frame: LongConnFrame) -> bool:
        """完成等待中的请求"""
        if not request_id:
            return False
            
        with self.pending_lock:
            future = self.pending.pop(request_id, None)
            
        if future and not future.done():
            future.set_result(frame)
            return True
        return False
    
    def _fail_all_pending(self, error: Exception) -> None:
        """失败所有等待中的请求"""
        with self.pending_lock:
            pending = self.pending.copy()
            self.pending.clear()
            
        for request_id, future in pending.items():
            if not future.done():
                try:
                    future.set_exception(error)
                except Exception as e:
                    logger.debug(f"[LongConnBot] Failed to set exception for request {request_id}: {e}")
    
    def _set_conn(self, conn: websockets.WebSocketClientProtocol) -> None:
        """设置当前连接"""
        with self.conn_lock:
            self.conn = conn
    
    def _release_conn(self, conn: websockets.WebSocketClientProtocol, error: Exception) -> None:
        """释放当前连接"""
        with self.conn_lock:
            if self.conn == conn:
                self.conn = None
        
        if conn:
            asyncio.create_task(conn.close())
        
        if error:
            self._fail_all_pending(error)
    
    def _current_conn(self) -> Optional[websockets.WebSocketClientProtocol]:
        """获取当前连接"""
        with self.conn_lock:
            return self.conn
    
    async def send_markdown(self, chat_id: str, content: str) -> None:
        """主动发送 Markdown 消息"""
        if not chat_id:
            raise ValueError("chat_id is required")
            
        request_id = self.generate_request_id()
        body = {
            "chatid": chat_id,
            "msgtype": "markdown",
            "markdown": {"content": content}
        }
        
        try:
            await self._send_request_and_wait(LongConnCmd.SEND_MSG, request_id, body)
            logger.debug(f"[LongConnBot] → Sent markdown to {chat_id}: {content[:50]}...")
        except Exception as e:
            logger.error(f"[LongConnBot] Failed to send markdown: {e}")
            raise
    
    async def send_text(self, chat_id: str, content: str) -> None:
        """主动发送文本消息"""
        if not chat_id:
            raise ValueError("chat_id is required")
            
        request_id = self.generate_request_id()
        body = {
            "chatid": chat_id,
            "msgtype": "text",
            "text": {"content": content}
        }
        
        try:
            await self._send_request_and_wait(LongConnCmd.SEND_MSG, request_id, body)
            logger.debug(f"[LongConnBot] → Sent text to {chat_id}: {content[:50]}...")
        except Exception as e:
            logger.error(f"[LongConnBot] Failed to send text: {e}")
            raise
    
    async def close(self) -> None:
        """关闭长连接机器人"""
        with self.close_once:
            if self.closed_event.is_set():
                logger.debug("[LongConnBot] Already closed")
                return
            self.closed_event.set()
        
        logger.debug("[LongConnBot] Closing bot...")
        self.running = False
        
        # 先清理待处理的请求，避免在关闭时继续发送
        self._fail_all_pending(LongConnError("Bot closed"))
        
        # 关闭 WebSocket 连接
        conn = self._current_conn()
        if conn:
            try:
                # 使用短超时，避免阻塞
                close_task = asyncio.create_task(conn.close())
                await asyncio.wait_for(close_task, timeout=1.0)
                logger.debug("[LongConnBot] WebSocket closed gracefully")
            except asyncio.TimeoutError:
                logger.debug("[LongConnBot] WebSocket close timeout, forcing close")
                # 强制关闭
                try:
                    if hasattr(conn, 'transport') and conn.transport:
                        conn.transport.close()
                except Exception:
                    pass
            except Exception as e:
                logger.debug(f"[LongConnBot] Error closing WebSocket: {e}")
        
        logger.info(f"[LongConnBot] Bot closed")
    
    async def _cleanup(self) -> None:
        """清理资源"""
        conn = self._current_conn()
        if conn:
            self._release_conn(conn, LongConnError("cleanup"))
class WeComChannel(BaseChannel):
    """企业微信频道"""
    
    name = "wecom"
    
    def __init__(self, config: Any):
        super().__init__(config)
        self.bot_id = getattr(config, "bot_id", "")
        self.secret = getattr(config, "secret", "")
        self.enabled = getattr(config, "enabled", True)
        self.websocket_url = getattr(config, "websocket_url", "wss://openws.work.weixin.qq.com")
        
        self.bot: Optional[LongConnBot] = None
        self.start_task: Optional[asyncio.Task] = None
        self.stop_event = asyncio.Event()
        self._http: Optional[httpx.AsyncClient] = None
    
    async def start(self) -> None:
        """启动频道"""
        if not WEBSOCKETS_AVAILABLE:
            logger.error("websockets library not installed. Run: pip install websockets")
            return
            
        if not self.bot_id or not self.secret:
            logger.error("[WeCom] Missing bot_id or secret")
            return
        
        if not self.enabled:
            logger.info("[WeCom] Channel disabled")
            return
        
        self._running = True
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0))
        logger.info(f"[WeCom] Starting channel...")
        
        # 创建长连接机器人
        self.bot = LongConnBot(
            bot_id=self.bot_id, 
            secret=self.secret, 
            handler=self._handle_message_wrapper,
            websocket_url=self.websocket_url
        )
        
        # 启动机器人
        self.start_task = asyncio.create_task(self.bot.start(self.stop_event))
        
        try:
            await self.start_task
        except asyncio.CancelledError:
            self._running = False
            pass
        except LongConnPermanentError as e:
            self._running = False
            logger.error(f"[WeCom] Start error: {e}")
            raise
        except Exception as e:
            self._running = False
            logger.error(f"[WeCom] Start error: {e}")
    
    async def _handle_message_wrapper(self, sender_id: str, chat_id: str, content: str, metadata: Dict[str, Any], stream_handler=None) -> Optional[str]:
        """处理收到的消息 - 支持流式回复"""
        try:
            media_files = await self._resolve_inbound_media(metadata)
            effective_content = format_inbound_media_text(media_files, content) if media_files else content

            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content=effective_content,
                media=media_files or None,
                metadata=metadata
            )
            return None
            
        except Exception as e:
            logger.error(f"[WeCom] Message handler error: {e}")
            if stream_handler:
                await stream_handler("处理消息时发生错误，请稍后重试。", is_final=True)
            return None

    async def _maybe_send_via_active_stream(
        self,
        msg: OutboundMessage,
        text: str,
    ) -> bool:
        if not self.bot:
            return False

        metadata = msg.metadata or {}
        message_id = str(metadata.get("_wecom_stream_message_id") or "").strip()
        frame_headers = metadata.get("_wecom_frame_headers") or {}
        req_id = str(frame_headers.get("req_id") or "").strip()
        if not message_id or not req_id:
            return False

        state = self.bot.get_stream_state(message_id)
        if not state or state.finished:
            return False

        content_to_send, msg_items = self.bot.prepare_reply_payload(text, metadata)
        if not content_to_send and not msg_items:
            return False

        await self.bot.send_stream_reply(
            LongConnFrame(headers=dict(frame_headers)),
            state.stream_id,
            content_to_send,
            finish=True,
            msg_items=msg_items or None,
        )
        state.finished = True
        self.bot.delete_stream_state(message_id)
        logger.debug(f"[WeCom] Reused passive stream for outbound reply: {message_id}")
        return True
    
    async def send(self, msg: OutboundMessage) -> None:
        """发送消息"""
        if not self.bot:
            logger.warning("[WeCom] Bot not initialized")
            return
        
        try:
            text = str(msg.content or "").strip()
            if msg.media:
                raise ValueError(
                    "WeCom 长连接模式不支持主动发送附件。"
                    "当前仅支持接收入站附件，以及在本轮被动回复中附带图片。"
                )
            if text:
                reused_stream = await self._maybe_send_via_active_stream(msg, text)
                if not reused_stream:
                    await self.bot.send_markdown(msg.chat_id, text)
            logger.debug(f"[WeCom] → Sent to {msg.chat_id}")
        except Exception as e:
            logger.error(f"[WeCom] Failed to send message: {e}")
    
    async def stop(self) -> None:
        """停止频道"""
        if not self._running:
            logger.debug("[WeCom] Channel already stopped")
            return
            
        logger.info("[WeCom] Stopping channel...")
        self._running = False
        self.stop_event.set()
        
        # 先关闭 bot
        if self.bot:
            try:
                await asyncio.wait_for(self.bot.close(), timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("[WeCom] Bot close timeout")
            except Exception as e:
                logger.debug(f"[WeCom] Error closing bot: {e}")
        
        # 再取消启动任务
        if self.start_task and not self.start_task.done():
            self.start_task.cancel()
            try:
                await asyncio.wait_for(self.start_task, timeout=1.0)
            except asyncio.TimeoutError:
                logger.debug("[WeCom] Start task cancel timeout")
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug(f"[WeCom] Error cancelling start task: {e}")

        if self._http:
            await self._http.aclose()
            self._http = None
        
        logger.info("[WeCom] Channel stopped")

    async def _resolve_inbound_media(self, metadata: Dict[str, Any]) -> List[str]:
        """解析并下载企业微信入站附件。"""
        attachments = self._collect_inbound_attachments(metadata)
        if not attachments:
            return []

        media_files: List[str] = []
        for attachment in attachments:
            try:
                local_path = await self._download_wecom_media(
                    url=attachment["url"],
                    aes_key=attachment["aes_key"],
                    message_id=metadata.get("msgid"),
                    filename=attachment.get("filename"),
                )
                if local_path:
                    media_files.append(local_path)
            except Exception as e:
                logger.error(f"[WeCom] Failed to download inbound attachment: {e}")

        return media_files

    @staticmethod
    def _collect_inbound_attachments(metadata: Dict[str, Any]) -> List[Dict[str, Optional[str]]]:
        """从企业微信回调体中提取附件信息。"""
        attachments: List[Dict[str, Optional[str]]] = []
        msg_type = metadata.get("msgtype", "")

        if msg_type == "image":
            image = metadata.get("image", {}) or {}
            if image.get("url") and image.get("aeskey"):
                attachments.append(
                    {
                        "url": image.get("url"),
                        "aes_key": image.get("aeskey"),
                        "filename": image.get("filename"),
                    }
                )
        elif msg_type == "file":
            file_info = metadata.get("file", {}) or {}
            if file_info.get("url") and file_info.get("aeskey"):
                attachments.append(
                    {
                        "url": file_info.get("url"),
                        "aes_key": file_info.get("aeskey"),
                        "filename": file_info.get("filename") or file_info.get("name"),
                    }
                )
        elif msg_type == "mixed":
            for item in (metadata.get("mixed", {}) or {}).get("msg_item", []) or []:
                item_type = item.get("msgtype")
                if item_type == "image":
                    image = item.get("image", {}) or {}
                    if image.get("url") and image.get("aeskey"):
                        attachments.append(
                            {
                                "url": image.get("url"),
                                "aes_key": image.get("aeskey"),
                                "filename": image.get("filename"),
                            }
                        )
                elif item_type == "file":
                    file_info = item.get("file", {}) or {}
                    if file_info.get("url") and file_info.get("aeskey"):
                        attachments.append(
                            {
                                "url": file_info.get("url"),
                                "aes_key": file_info.get("aeskey"),
                                "filename": file_info.get("filename") or file_info.get("name"),
                            }
                        )

        return attachments

    async def _download_wecom_media(
        self,
        *,
        url: str,
        aes_key: str,
        message_id: Optional[str],
        filename: Optional[str] = None,
    ) -> Optional[str]:
        """下载并解密企业微信 bot-ws 附件。"""
        if not self._http:
            return None

        response = await self._http.get(url, follow_redirects=True)
        response.raise_for_status()
        encrypted = await response.aread()
        decrypted = decrypt_wecom_media_bytes(encrypted, aes_key)

        resolved_filename = (
            filename
            or extract_filename_from_content_disposition(response.headers.get("content-disposition"))
        )
        content_type = response.headers.get("content-type")
        local_path = save_bytes_to_temp(
            self.name,
            decrypted,
            message_id=message_id,
            filename=resolved_filename,
            content_type=content_type,
            prefix="wecom_attachment",
        )
        logger.info(f"[WeCom] Inbound attachment saved: {local_path}")
        return local_path

    async def test_connection(self) -> Dict[str, Any]:
        """测试连接 - 验证企业微信凭据"""
        if not WEBSOCKETS_AVAILABLE:
            return {"success": False, "message": "websockets library not installed"}
            
        if not self.bot_id or not self.secret:
            return {"success": False, "message": "Bot ID or Secret not configured"}
        
        # 验证 Bot ID 格式
        if len(self.bot_id) < 8:
            return {"success": False, "message": "Invalid Bot ID format - Bot ID should be at least 8 characters"}
        
        # 验证 Secret 格式
        if len(self.secret) < 16:
            return {"success": False, "message": "Invalid Secret format - Secret should be at least 16 characters"}
        
        # 验证 Bot ID 格式（企业微信 Bot ID 通常是字母数字组合）
        if not all(c.isalnum() or c in '-_' for c in self.bot_id):
            return {"success": False, "message": "Invalid Bot ID format - should contain only letters, numbers, hyphens and underscores"}
        
        # 验证 Secret 格式（通常是字母数字组合）
        if not all(c.isalnum() or c in '-_' for c in self.secret):
            return {"success": False, "message": "Invalid Secret format - should contain only letters, numbers, hyphens and underscores"}
        
        # 验证 WebSocket URL 格式
        if not self.websocket_url.startswith(('ws://', 'wss://')):
            return {"success": False, "message": "Invalid WebSocket URL format - should start with ws:// or wss://"}
        
        try:
            import asyncio
            import websockets
            import json
            import time
            
            # 生成请求ID
            request_id = f"test_{int(time.time() * 1000)}"
            
            # 构建订阅命令（企业微信使用 aibot_subscribe 进行认证）
            subscribe_message = {
                "cmd": "aibot_subscribe",
                "headers": {
                    "req_id": request_id
                },
                "body": {
                    "bot_id": self.bot_id,
                    "secret": self.secret
                }
            }
            
            # 尝试连接并认证
            try:
                websocket = await asyncio.wait_for(
                    websockets.connect(
                        self.websocket_url,
                        ping_interval=None,  # 测试时禁用自动ping
                        close_timeout=3
                    ), 
                    timeout=5.0
                )
                
                try:
                    # 发送订阅命令
                    await asyncio.wait_for(
                        websocket.send(json.dumps(subscribe_message)),
                        timeout=3.0
                    )
                    
                    # 等待响应
                    response_text = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=5.0
                    )
                    response_data = json.loads(response_text)
                    
                    # 检查认证结果
                    # 企业微信返回格式: {"errcode": 0, "errmsg": "ok"} 表示成功
                    err_code = response_data.get("err_code", response_data.get("errcode", -1))
                    err_msg = response_data.get("err_msg", response_data.get("errmsg", ""))
                    
                    # 如果响应中没有 err_code，检查是否有其他成功标识
                    if err_code == -1 and response_data.get("cmd") == "aibot_subscribe":
                        # 可能是成功响应但没有明确的 err_code
                        return {
                            "success": True,
                            "message": "WeCom credentials verified successfully - connection test passed",
                            "bot_info": {
                                "bot_id": self.bot_id[:12] + "...",
                                "ws_url": self.websocket_url,
                                "status": "credentials_verified",
                                "note": "Successfully authenticated with WeCom API"
                            }
                        }
                    
                    if err_code == 0:
                        return {
                            "success": True,
                            "message": "WeCom credentials verified successfully - connection test passed",
                            "bot_info": {
                                "bot_id": self.bot_id[:12] + "...",
                                "ws_url": self.websocket_url,
                                "status": "credentials_verified",
                                "note": "Successfully authenticated with WeCom API"
                            }
                        }
                    elif err_code == 40001:
                        return {
                            "success": False,
                            "message": "Invalid Bot ID or Secret - authentication failed (error code: 40001)"
                        }
                    elif err_code == 40014:
                        return {
                            "success": False,
                            "message": "Invalid Bot ID or Secret - bot not found or disabled (error code: 40014)"
                        }
                    elif err_code == 93019:
                        return {
                            "success": False,
                            "message": "Invalid Bot ID - bot not found or incorrect format (error code: 93019)"
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"Invalid Bot ID or Secret - credentials rejected by WeCom: {err_msg} (code: {err_code})"
                        }
                finally:
                    # 确保关闭 websocket 连接
                    try:
                        await websocket.close()
                    except Exception:
                        pass
                        
            except asyncio.TimeoutError:
                return {
                    "success": False,
                    "message": "Connection timeout - check your network connection or WeCom API status"
                }
            except websockets.exceptions.InvalidURI:
                return {
                    "success": False,
                    "message": "Invalid WebSocket URL - check the websocket_url configuration"
                }
            except (websockets.exceptions.ConnectionClosed, websockets.exceptions.ConnectionClosedError) as e:
                return {
                    "success": False,
                    "message": f"Connection closed by server - check your Bot ID and Secret (code: {e.code if hasattr(e, 'code') else 'unknown'})"
                }
            except json.JSONDecodeError:
                return {
                    "success": False,
                    "message": "Invalid response format from WeCom server"
                }
                
        except ImportError:
            return {
                "success": False,
                "message": "websockets library not installed. Run: pip install websockets"
            }
        except Exception as e:
            logger.error(f"[WeCom] Test connection error: {e}")
            return {
                "success": False,
                "message": f"Network error - unable to reach WeCom API: {str(e)}"
            }
    
    @property
    def display_name(self) -> str:
        return "企业微信"
