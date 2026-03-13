"""小智AI频道模块

作为 MCP Client 连接到小智AI的 MCP Server。

支持两种模式：
1. 工具调用模式（默认）：小智AI直接调用已注册工具
2. 对话模式：小智AI通过 send_message 工具发送用户消息 → Agent 处理 → 返回响应

配置方式：
1. 在小智AI后台获取 MCP Endpoint URL（包含 token）
2. 将该 URL 填入本系统的小智AI频道配置
3. 启用频道后，系统会作为 MCP Client 连接到小智AI

流程：
用户语音 -> 小智机器人 -> 小智AI LLM -> MCP工具调用 -> 本项目处理 -> 返回结果 -> 语音播报
"""

import asyncio
import json
from typing import Any

import websockets
from loguru import logger

from backend.modules.channels.base import BaseChannel, OutboundMessage


class XiaozhiChannel(BaseChannel):
    """小智AI MCP Client 频道
    
    作为 MCP Client 连接到小智AI的 MCP Server。
    
    配置项（对应 XiaozhiConfig）：
    - endpoint: 小智AI后台生成的 MCP Endpoint URL（包含 token）
    - enable_conversation: 是否启用对话模式（默认 False）
    - allow_from: 用户白名单（可选）
    """

    name = "xiaozhi"

    def __init__(self, config: Any):
        super().__init__(config)
        self._websocket = None
        self._reconnect_delay = 5
        self._max_reconnect_delay = 300
        self._current_reconnect_delay = self._reconnect_delay
        self._initialized = False
        self._pending_responses: dict[int, asyncio.Future] = {}

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """启动频道，连接到小智AI MCP Server"""
        if not self.config.endpoint:
            logger.error("XiaozhiAI MCP endpoint not configured")
            return

        self._running = True
        logger.info("=" * 60)
        logger.info("Starting XiaozhiAI channel")
        logger.info(f"Endpoint: {self.config.endpoint}")
        logger.info(f"Conversation mode: {getattr(self.config, 'enable_conversation', False)}")
        logger.info("=" * 60)

        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                logger.info("XiaozhiAI channel cancelled")
                self._running = False
                break
            except Exception as e:
                if not self._running:
                    logger.debug("Connection error during shutdown, ignoring")
                    break
                logger.error(f"XiaozhiAI connection error: {e}")
                logger.info(f"Reconnecting in {self._current_reconnect_delay}s...")
                try:
                    await asyncio.sleep(self._current_reconnect_delay)
                except asyncio.CancelledError:
                    logger.info("Reconnect cancelled")
                    break
                self._current_reconnect_delay = min(
                    self._current_reconnect_delay * 2,
                    self._max_reconnect_delay,
                )
        
        logger.info("XiaozhiAI channel start loop exited")

    async def _connect_and_listen(self) -> None:
        """建立 WebSocket 连接并监听消息"""
        logger.info(f"Attempting to connect to XiaozhiAI: {self.config.endpoint}")
        message_count = 0
        try:
            async with websockets.connect(
                self.config.endpoint,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=10,
            ) as websocket:
                self._websocket = websocket
                self._current_reconnect_delay = self._reconnect_delay
                logger.info("✓ XiaozhiAI MCP connected successfully!")
                logger.info("Waiting for messages from XiaozhiAI...")

                async for message in websocket:
                    message_count += 1
                    logger.debug(f"<<< [{message_count}] Received from XiaozhiAI: {message[:500]}")
                    try:
                        await self._handle_mcp_message(message)
                    except Exception as e:
                        logger.error(f"Error handling MCP message #{message_count}: {e}", exc_info=True)
        except websockets.exceptions.ConnectionClosed as e:
            if self._running:
                logger.warning(f"WebSocket connection closed: {e}")
            else:
                logger.debug(f"WebSocket closed during shutdown: {e}")
            raise
        except websockets.exceptions.WebSocketException as e:
            if self._running:
                logger.error(f"WebSocket error: {e}")
            else:
                logger.debug(f"WebSocket error during shutdown: {e}")
            raise
        finally:
            self._websocket = None
            self._initialized = False
            # 只在连接意外断开时清理响应（正常关闭时已在 stop() 中清理）
            if self._running and self._pending_responses:
                for msg_id, future in list(self._pending_responses.items()):
                    if not future.done():
                        try:
                            future.set_exception(ConnectionError("WebSocket connection lost"))
                        except Exception:
                            pass
                self._pending_responses.clear()
                logger.info("XiaozhiAI connection lost, cleaned up pending responses")
            else:
                logger.debug("XiaozhiAI connection closed")

    async def stop(self) -> None:
        """停止频道"""
        if not self._running:
            logger.debug("XiaozhiAI channel already stopped")
            return
            
        self._running = False
        logger.info("Stopping XiaozhiAI channel...")
        
        # 清理待处理的响应
        if self._pending_responses:
            logger.debug(f"Cleaning up {len(self._pending_responses)} pending responses")
            for msg_id, future in list(self._pending_responses.items()):
                if not future.done():
                    try:
                        future.set_exception(asyncio.CancelledError("Channel stopping"))
                    except Exception:
                        pass
            self._pending_responses.clear()
        
        # 关闭 WebSocket 连接
        if self._websocket:
            try:
                # 使用更短的超时，避免阻塞关闭流程
                close_task = asyncio.create_task(self._websocket.close())
                await asyncio.wait_for(close_task, timeout=1.0)
                logger.debug("WebSocket closed gracefully")
            except asyncio.TimeoutError:
                logger.warning("WebSocket close timeout, forcing close")
                # 强制关闭
                try:
                    if hasattr(self._websocket, 'transport') and self._websocket.transport:
                        self._websocket.transport.close()
                except Exception:
                    pass
            except Exception as e:
                logger.debug(f"Error closing WebSocket: {e}")
            finally:
                self._websocket = None
                
        self._initialized = False
        logger.info("XiaozhiAI channel stopped")

    # ------------------------------------------------------------------
    # MCP 协议处理
    # ------------------------------------------------------------------

    async def _handle_mcp_message(self, message: str) -> None:
        """处理接收到的 MCP 消息"""
        try:
            data = json.loads(message)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse MCP message: {e}, raw: {message[:200]}")
            return

        if "jsonrpc" not in data:
            logger.debug(f"Non-MCP message: {data}")
            return

        method = data.get("method", "")
        msg_id = data.get("id")
        params = data.get("params", {})
        
        if method == "tools/call":
            logger.info(f"MCP tools/call - id={msg_id}, tool={params.get('name', 'unknown')}")
        else:
            logger.debug(f"MCP method={method} id={msg_id}")

        if method == "initialize":
            await self._handle_initialize(msg_id, params)
        elif method == "notifications/initialized":
            logger.debug("Client initialization completed")
        elif method == "ping":
            await self._send_mcp({"jsonrpc": "2.0", "id": msg_id, "result": {}})
        elif method == "tools/list":
            await self._handle_tools_list(msg_id)
        elif method == "tools/call":
            await self._handle_tool_call(msg_id, params)
        elif method == "notifications/message":
            await self._handle_notification(params)
        else:
            logger.warning(f"Unknown MCP method: {method}")

    async def _handle_initialize(self, msg_id: int, params: dict) -> None:
        """处理 MCP initialize 请求"""
        client_name = params.get("clientInfo", {}).get("name", "unknown")
        logger.debug(f"MCP initialize from {client_name}")
        await self._send_mcp({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "countbot-mcp-server", "version": "1.0.0"},
            },
        })
        self._initialized = True
        logger.info("MCP initialization completed")

    async def _handle_tools_list(self, msg_id: int) -> None:
        """处理 MCP tools/list 请求，返回可用工具列表"""
        try:
            from backend.app import get_tool_registry
            tool_registry = get_tool_registry()
            tools = []
            if tool_registry:
                enable_conversation = getattr(self.config, "enable_conversation", False)
                
                if enable_conversation:
                    # 对话模式：只返回 send_message 工具
                    tool = tool_registry.get_tool("send_message")
                    if tool:
                        defn = tool.get_definition()
                        tools.append({
                            "name": tool.name,
                            "description": defn.get("description", ""),
                            "inputSchema": defn.get("parameters", defn.get("inputSchema", {})),
                        })
                        logger.debug("Conversation mode: send_message tool registered")
                    else:
                        logger.error("Conversation mode enabled but send_message tool not found in registry!")
                        logger.error(f"Available tools: {tool_registry.list_tools()}")
                else:
                    # 工具调用模式：返回所有工具
                    names = tool_registry.list_tools()
                    for tool_name in names:
                        tool = tool_registry.get_tool(tool_name)
                        if tool:
                            defn = tool.get_definition()
                            tools.append({
                                "name": tool.name,
                                "description": defn.get("description", ""),
                                "inputSchema": defn.get("parameters", defn.get("inputSchema", {})),
                            })
                    logger.debug(f"Tool mode: {len(tools)} tools available")
                    
            await self._send_mcp({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools}})
            logger.debug(f"Sent {len(tools)} tools to XiaozhiAI (conversation_mode={enable_conversation})")
        except Exception as e:
            logger.error(f"tools/list error: {e}", exc_info=True)
            await self._send_mcp({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": []}})

    async def _handle_tool_call(self, msg_id: int, params: dict) -> None:
        """处理 MCP tools/call 请求，执行工具调用"""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        logger.debug(f"[TOOL_CALL] id={msg_id}, tool={tool_name}, args={arguments}")

        try:
            if tool_name == "send_message" and getattr(self.config, "enable_conversation", False):
                # 对话模式：处理 send_message 工具调用
                user_message = arguments.get("message") or arguments.get("text", "")
                
                if not user_message:
                    logger.warning(f"[TOOL_CALL] Empty arguments! Full params: {params}")
                    error_msg = (
                        "❌ 参数错误：缺少必需的消息内容\n\n"
                        "正确用法：\n"
                        "send_message({\"text\": \"用户说的话\"})\n"
                        "或\n"
                        "send_message({\"message\": \"用户说的话\"})\n\n"
                        "示例：\n"
                        "send_message({\"text\": \"帮我查一下天气\"})\n"
                        "send_message({\"message\": \"你好吗\"})\n\n"
                        "⚠️ 注意：必须传递 text 或 message 参数，不能为空！"
                    )
                    await self._send_mcp({
                        "jsonrpc": "2.0", "id": msg_id,
                        "result": {"content": [{"type": "text", "text": error_msg}]},
                    })
                    logger.info(f"[TOOL_CALL] Sent error response for id={msg_id}")
                    return

                logger.info(f"Processing message: {user_message[:50]}...")
                response_future: asyncio.Future = asyncio.get_event_loop().create_future()
                self._pending_responses[msg_id] = response_future

                await self._handle_message(
                    sender_id="xiaozhi_user",
                    chat_id="xiaozhi_chat",
                    content=user_message,
                    metadata={"source": "send_message_tool", "mcp_message_id": msg_id},
                )

                try:
                    agent_response = await asyncio.wait_for(response_future, timeout=120.0)
                    response = {
                        "jsonrpc": "2.0", "id": msg_id,
                        "result": {"content": [{"type": "text", "text": agent_response}]},
                    }
                    logger.debug(f"Agent response ready for msg_id {msg_id}")
                except asyncio.TimeoutError:
                    logger.error(f"Agent response timeout (120s) for message: {user_message[:50]}")
                    response = {
                        "jsonrpc": "2.0", "id": msg_id,
                        "result": {"content": [{"type": "text", "text": "处理超时，请稍后重试"}]},
                    }
                except ConnectionError as e:
                    logger.error(f"Connection lost while waiting for response: {e}")
                    return
                finally:
                    self._pending_responses.pop(msg_id, None)

            else:
                # 工具调用模式：直接执行工具
                from backend.app import get_tool_registry
                tool_registry = get_tool_registry()
                if not tool_registry:
                    raise RuntimeError("Tool registry not available")
                result = await tool_registry.execute(tool_name, arguments, auto_record=False)
                response = {
                    "jsonrpc": "2.0", "id": msg_id,
                    "result": {"content": [{"type": "text", "text": str(result)}]},
                }

        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            response = {
                "jsonrpc": "2.0", "id": msg_id,
                "error": {"code": -32603, "message": f"Tool execution failed: {e}"},
            }

        await self._send_mcp(response)

    async def _handle_notification(self, params: dict) -> None:
        """处理 MCP notifications/message"""
        message = params.get("message", "")
        if not message:
            return
        logger.info(f"XiaozhiAI notification: {message[:50]}...")
        await self._handle_message(
            sender_id="xiaozhi_user",
            chat_id="xiaozhi_chat",
            content=message,
            metadata={"level": params.get("level", "info"), "source": "xiaozhi_notification"},
        )

    async def _send_mcp(self, message: dict) -> None:
        """发送 MCP 消息到小智AI"""
        if not self._websocket:
            logger.warning("Cannot send MCP message: not connected")
            return
        try:
            msg_str = json.dumps(message)
            await self._websocket.send(msg_str)
            logger.debug(f">>> Sent MCP message: id={message.get('id', 'N/A')}, method={message.get('method', 'response')}")
            logger.debug(f">>> Full message: {msg_str[:200]}")
        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"WebSocket connection closed while sending: {e}")
            self._websocket = None
            self._initialized = False
        except Exception as e:
            logger.error(f"Failed to send MCP message: {e}")

    # ------------------------------------------------------------------
    # 出站消息
    # ------------------------------------------------------------------

    async def send(self, msg: OutboundMessage) -> None:
        """发送出站消息
        
        如果消息包含 mcp_message_id，则作为工具调用响应返回；
        否则作为通知消息推送。
        """
        if not self._websocket or not self._initialized:
            logger.warning("XiaozhiAI not connected/initialized")
            return

        mcp_message_id = (msg.metadata or {}).get("mcp_message_id")
        if mcp_message_id is not None and mcp_message_id in self._pending_responses:
            future = self._pending_responses[mcp_message_id]
            if not future.done():
                logger.debug(f"Setting response for mcp_message_id {mcp_message_id}")
                future.set_result(msg.content)
            else:
                logger.warning(f"Future for mcp_message_id {mcp_message_id} already done")
            return

        # 普通通知推送
        logger.debug(f"Sending notification message: {msg.content[:100]}")
        await self._send_mcp({
            "jsonrpc": "2.0",
            "method": "notifications/message",
            "params": {"level": "info", "message": msg.content},
        })

    # ------------------------------------------------------------------
    # 连接测试
    # ------------------------------------------------------------------

    async def test_connection(self) -> dict[str, Any]:
        """测试与小智AI的连接
        
        执行完整的 MCP 协议握手来验证连接是否正常。
        """
        if not self.config.endpoint:
            return {"success": False, "message": "MCP 接入点未配置"}
        if not self.config.endpoint.startswith(("ws://", "wss://")):
            return {"success": False, "message": "接入点格式无效，须以 ws:// 或 wss:// 开头"}
        
        try:
            async with websockets.connect(
                self.config.endpoint,
                ping_interval=None,
                close_timeout=5,
                open_timeout=10
            ) as ws:
                # 等待 initialize 请求
                try:
                    init_msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    init_data = json.loads(init_msg)
                    
                    if init_data.get("method") != "initialize":
                        return {
                            "success": False,
                            "message": f"未收到 initialize 请求，收到: {init_data.get('method', 'unknown')}"
                        }
                    
                    # 发送 initialize 响应
                    init_response = {
                        "jsonrpc": "2.0",
                        "id": init_data.get("id"),
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": "countbot-test", "version": "1.0.0"},
                        },
                    }
                    await ws.send(json.dumps(init_response))
                    
                    # 等待 notifications/initialized
                    try:
                        notif_msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
                        notif_data = json.loads(notif_msg)
                        
                        if notif_data.get("method") == "notifications/initialized":
                            return {
                                "success": True,
                                "message": "连接测试成功，MCP 协议握手完成",
                                "bot_info": {
                                    "endpoint": self.config.endpoint,
                                    "status": "connected",
                                    "protocol": "MCP 2024-11-05"
                                },
                            }
                    except asyncio.TimeoutError:
                        # 有些实现可能不发送 notifications/initialized
                        return {
                            "success": True,
                            "message": "连接测试成功（未收到 initialized 通知，但连接正常）",
                            "bot_info": {
                                "endpoint": self.config.endpoint,
                                "status": "connected"
                            },
                        }
                    
                except asyncio.TimeoutError:
                    return {
                        "success": False,
                        "message": "连接超时，未收到 initialize 请求"
                    }
                except json.JSONDecodeError as e:
                    return {
                        "success": False,
                        "message": f"消息格式错误: {e}"
                    }
                    
        except websockets.exceptions.InvalidStatusCode as e:
            return {
                "success": False,
                "message": f"连接被拒绝 (HTTP {e.status_code})，请检查 Token 是否有效"
            }
        except websockets.exceptions.WebSocketException as e:
            return {
                "success": False,
                "message": f"WebSocket 错误: {e}"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"连接失败: {e}"
            }
        
        return {
            "success": False,
            "message": "未知错误"
        }

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def display_name(self) -> str:
        return "小智AI"

