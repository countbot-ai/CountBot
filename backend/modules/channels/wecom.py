"""企业微信频道模块

基于 WebSocket 长连接的企业微信机器人实现。
支持流式回复和实时消息处理。
"""

import asyncio
import json
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional, Dict, List, Callable
import threading
import re

from loguru import logger

from backend.modules.channels.base import BaseChannel, InboundMessage, OutboundMessage

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
        self.write_lock = threading.Lock()
        
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
    
    async def send_stream_reply(self, frame: LongConnFrame, stream_id: str, text: str, finish: bool = False) -> None:
        """发送流式回复"""
        normalized_text = normalize_thinking_tags(text)
        if not normalized_text and not finish:
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
        
        request = LongConnRequest(
            cmd=LongConnCmd.RESPOND_MSG,
            headers={"req_id": frame.headers.get("req_id", "")},
            body=reply_body
        )
        
        await self._write_json(conn, request.to_dict())
        logger.debug(f"[LongConnBot] → Stream reply sent (finish={finish}): {normalized_text[:50]}...")
    
    async def send_thinking_reply(self, frame: LongConnFrame, stream_id: str) -> None:
        """发送思考提示"""
        try:
            await self.send_stream_reply(frame, stream_id, self.thinking_message, finish=False)
        except Exception as e:
            logger.error(f"[LongConnBot] Failed to send thinking reply: {e}")
    
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
                    raise e.args[0] if e.args else e
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
        sender_id = frame.body.get("from", {}).get("userid", "")
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
        
        if not content:
            return
            
        logger.info(f"[LongConnBot] ← Message from {sender_id}: {content[:50]}...")
        
        # 初始化流式状态
        stream_id = self.generate_request_id()
        request_id = frame.headers.get("req_id", "")
        
        stream_state = StreamState(
            stream_id=stream_id,
            request_id=request_id
        )
        self.set_stream_state(message_id, stream_state)
        
        # 发送思考提示
        await self.send_thinking_reply(frame, stream_id)
        
        if self.handler:
            try:
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
                            visible_text=state.accumulated_text,
                            finish=True
                        )
                        
                        logger.info(f"[LongConnBot] Final reply: {len(content_to_send)} chars")
                        await self.send_stream_reply(frame, stream_id, content_to_send, finish=True)
                        
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
                        visible_text=state.accumulated_text,
                        finish=False
                    )
                    
                    await self.send_stream_reply(frame, stream_id, content_to_send, finish=False)
                    state.last_send_time = time.time() * 1000
                    state.message_count += 1
                
                # 通过 metadata 传递流式处理器
                metadata = frame.body.copy()
                metadata['_stream_handler'] = stream_handler
                
                await self.handler(sender_id, chat_id, content, metadata)
                
            except Exception as e:
                logger.error(f"[LongConnBot] Handler error: {e}")
                state = self.get_stream_state(message_id)
                if state:
                    await self.send_stream_reply(frame, stream_id, "处理消息时发生错误，请稍后重试。", finish=True)
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
                    if command == LongConnCmd.SUBSCRIBE and frame.err_code in [40001, 40014]:
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
        
        with self.write_lock:
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
            pass
        except Exception as e:
            logger.error(f"[WeCom] Start error: {e}")
    
    async def _handle_message_wrapper(self, sender_id: str, chat_id: str, content: str, metadata: Dict[str, Any], stream_handler=None) -> Optional[str]:
        """处理收到的消息 - 支持流式回复"""
        try:
            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content=content,
                metadata=metadata
            )
            return None
            
        except Exception as e:
            logger.error(f"[WeCom] Message handler error: {e}")
            if stream_handler:
                await stream_handler("处理消息时发生错误，请稍后重试。", is_final=True)
            return None
    
    async def send(self, msg: OutboundMessage) -> None:
        """发送消息"""
        if not self.bot:
            logger.warning("[WeCom] Bot not initialized")
            return
        
        try:
            await self.bot.send_markdown(msg.chat_id, msg.content)
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
        
        logger.info("[WeCom] Channel stopped")
    
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