"""MCP 服务器连接与连通性测试。"""

import asyncio
from contextlib import AsyncExitStack
from typing import Any, Dict, Optional

from loguru import logger

from backend.modules.config.schema import McpServerConfig
from backend.modules.tools.base import Tool
from backend.modules.tools.registry import ToolRegistry

from backend.modules.mcp.helpers import (
    _infer_transport,
    _normalize_windows_stdio_command,
    _qualify_name,
)
from backend.modules.mcp.wrappers import (
    MCPPromptWrapper,
    MCPResourceCatalogWrapper,
    MCPToolWrapper,
)


def _iter_exception_tree(exc: BaseException):
    """递归展开异常树（含 ExceptionGroup 与 __cause__）。

    MCP SDK 会把传输层的 httpx 异常包进 TaskGroup 的 ExceptionGroup，
    直接读最外层异常拿不到 HTTP 状态码，必须递归展开。
    """
    yield exc
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            yield from _iter_exception_tree(sub)
    elif exc.__cause__ is not None:
        yield from _iter_exception_tree(exc.__cause__)


def _extract_auth_status_codes(exc: BaseException) -> set[int]:
    """从异常树提取 401/403 状态码，用于认证失败分类。"""
    import httpx

    codes: set[int] = set()
    for e in _iter_exception_tree(exc):
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status in (401, 403):
            codes.add(status)
        elif isinstance(e, httpx.HTTPStatusError):
            pass  # response 已覆盖
    return codes


def _authed_http_client_factory(config: McpServerConfig, observed: list[int]):
    """为 SSE 传输构造带凭证、显式禁止跟随重定向的 httpx 客户端工厂。

    redirect:manual：Authorization 等凭证头不允许在 302/307 时发往其他
    源，防止 token 泄漏。SDK 2.x 默认已关闭重定向（转由传输层做同源内
    跟随），此处显式固化，避免未来 httpx/SDK 默认值变化引入泄漏面。

    observed：本次连接尝试的状态码记录器（闭包写入）。
    """
    import httpx
    from mcp.shared._httpx_utils import (
        MCP_DEFAULT_SSE_READ_TIMEOUT,
        MCP_DEFAULT_TIMEOUT,
    )

    async def _record(response) -> None:
        if response.status_code in (401, 403):
            observed.append(response.status_code)

    def factory(**kwargs):
        merged_headers = {**(kwargs.pop("headers", None) or {}), **(config.headers or {})}
        kwargs["headers"] = merged_headers or None
        kwargs.setdefault(
            "timeout",
            httpx.Timeout(MCP_DEFAULT_TIMEOUT, read=MCP_DEFAULT_SSE_READ_TIMEOUT),
        )
        kwargs["follow_redirects"] = False
        kwargs["event_hooks"] = {"response": [_record]}
        return httpx.AsyncClient(**kwargs)

    return factory


async def _establish_mcp_session(
    name: str,
    config: McpServerConfig,
    transport_type: str,
    connect_timeout: int,
):
    """建立传输与 MCP 会话，返回 (AsyncExitStack, ClientSession)。

    401/403 恰好重试一次：首次 401 可能来自凭证刚被轮换的竞态，重试可
    自愈；两次都 401/403 才判定为配置错误并给出分类日志。每次尝试使用
    全新的 AsyncExitStack，失败路径完整清理，避免连接池泄漏。
    """
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamable_http_client
    import httpx

    last_exc: BaseException | None = None
    for attempt in (1, 2):
        stack = AsyncExitStack()
        # 本次尝试的 401/403 观测：SDK 会把非 2xx 吞成 JSONRPCError，
        # 状态码只能从 httpx 的 response hook 拿到
        observed_codes: list[int] = []
        try:
            await stack.__aenter__()
            if transport_type == "stdio":
                command, args, env = _normalize_windows_stdio_command(
                    config.command, config.args, config.env,
                )
                from mcp.client.stdio import StdioServerParameters
                server_params = StdioServerParameters(
                    command=command,
                    args=args,
                    env=env or None,
                )
                read, write = await stack.enter_async_context(
                    stdio_client(server_params)
                )
            elif transport_type == "sse":
                read, write = await stack.enter_async_context(
                    sse_client(
                        url=config.url,
                        httpx_client_factory=_authed_http_client_factory(
                            config, observed_codes
                        ),
                    )
                )
            elif transport_type == "streamable_http":
                http_client = None
                if config.headers:
                    # 传入的 client 由调用方负责关闭，SDK 不会代为释放；
                    # 注册进 stack 才能随连接一起退出，否则每次连接都遗留
                    # 一个连接池。redirect:manual + 401/403 观测见下方 hook。
                    async def _record(response) -> None:
                        if response.status_code in (401, 403):
                            observed_codes.append(response.status_code)

                    http_client = await stack.enter_async_context(
                        httpx.AsyncClient(
                            headers=config.headers,
                            follow_redirects=False,
                            event_hooks={"response": [_record]},
                        )
                    )
                result = await stack.enter_async_context(
                    streamable_http_client(url=config.url, http_client=http_client)
                )
                read, write = result[0], result[1]
            else:
                raise ValueError(f"unknown transport '{transport_type}'")

            session = await asyncio.wait_for(
                stack.enter_async_context(ClientSession(read, write)),
                timeout=connect_timeout,
            )
            await asyncio.wait_for(session.initialize(), timeout=connect_timeout)
            return stack, session
        except Exception as exc:
            last_exc = exc
            codes = _extract_auth_status_codes(exc) | set(observed_codes)
            try:
                await stack.__aexit__(type(exc), exc, exc.__traceback__)
            except Exception:
                pass
            if codes & {401, 403} and attempt == 1:
                logger.warning(
                    f"MCP server '{name}': 认证被拒绝({sorted(codes)})，重试 1 次"
                )
                continue
            if codes & {401, 403}:
                logger.error(
                    f"MCP server '{name}': 认证被拒绝({sorted(codes)})，重试后仍失败，"
                    f"请检查 headers/env 凭证配置"
                )
            # 将观测到的状态码附加到异常，供调用方生成分类错误消息
            exc.auth_codes = codes  # type: ignore[attr-defined]
            raise
    raise last_exc  # pragma: no cover - 循环内必然 return 或 raise


async def connect_mcp_server(
    name: str,
    config: McpServerConfig,
    registry: ToolRegistry,
    out_wrappers: Optional[Dict[str, Tool]] = None,
) -> Optional[AsyncExitStack]:
    try:
        from mcp import ClientSession
    except ImportError:
        logger.error("mcp package not installed, run: pip install mcp")
        return None

    transport_type = _infer_transport(config)
    if not transport_type:
        logger.warning(f"MCP server '{name}': no command or url configured, skipping")
        return None

    # 传输级前置校验保留在调用方：给出与具体传输相关的精确 warning
    if transport_type == "stdio" and not config.command:
        logger.warning(f"MCP server '{name}': stdio transport requires 'command', skipping")
        return None
    if transport_type in ("sse", "streamable_http") and not config.url:
        logger.warning(f"MCP server '{name}': {transport_type} transport requires 'url', skipping")
        return None

    connect_timeout = config.connect_timeout or 10

    try:
        stack, session = await _establish_mcp_session(
            name, config, transport_type, connect_timeout
        )
    except asyncio.TimeoutError:
        logger.error(f"MCP server '{name}': connection timed out after {connect_timeout}s")
        return None
    except Exception as exc:
        logger.error(f"MCP server '{name}': connection failed: {type(exc).__name__}: {exc}")
        return None

    try:
        enabled_tools = set(config.include_tools or ["*"])
        allow_all = "*" in enabled_tools
        exclude_set = set(config.exclude_tools or [])
        tool_timeout = config.timeout or 30

        tools_result = await session.list_tools()
        registered = 0
        matched_tools: set[str] = set()
        available_raw: list[str] = []
        available_wrapped: list[str] = []

        for tool_def in tools_result.tools:
            wrapped_name = _qualify_name(name, tool_def.name)
            available_raw.append(tool_def.name)
            available_wrapped.append(wrapped_name)
            if not allow_all and tool_def.name not in enabled_tools and wrapped_name not in enabled_tools:
                continue
            if tool_def.name in exclude_set or wrapped_name in exclude_set:
                continue
            if tool_def.name in enabled_tools:
                matched_tools.add(tool_def.name)
            if wrapped_name in enabled_tools:
                matched_tools.add(wrapped_name)
            try:
                wrapper = MCPToolWrapper(session, name, tool_def, tool_timeout=tool_timeout)
                registry.register(wrapper)
                if out_wrappers is not None:
                    out_wrappers[wrapper.name] = wrapper
                registered += 1
            except ValueError:
                logger.warning(f"MCP tool '{wrapped_name}' already registered, skipping")

        if not allow_all and enabled_tools:
            unmatched = sorted(enabled_tools - matched_tools)
            if unmatched:
                logger.warning(
                    f"MCP server '{name}': include_tools entries not found: {unmatched}. "
                    f"Available: {available_raw[:20]}"
                )

        # 资源统一用一个通用工具暴露，而不是每个 resource 一个工具：
        # 服务器常提供几十个 resource，逐个注册会让工具面迅速膨胀，
        # 挤占模型对内置工具的选择注意力。
        if config.enable_resources:
            try:
                resources_result = await session.list_resources()
                resources = list(resources_result.resources)
                if resources:
                    try:
                        wrapper = MCPResourceCatalogWrapper(
                            session, name, resources, resource_timeout=tool_timeout
                        )
                        registry.register(wrapper)
                        if out_wrappers is not None:
                            out_wrappers[wrapper.name] = wrapper
                        registered += 1
                    except ValueError:
                        logger.debug("MCP resource catalog already registered, skipping")
            except Exception as exc:
                logger.debug(f"MCP server '{name}': resources not supported: {exc}")

        if config.enable_prompts:
            try:
                prompts_result = await session.list_prompts()
                for prompt in prompts_result.prompts:
                    try:
                        wrapper = MCPPromptWrapper(session, name, prompt, prompt_timeout=tool_timeout)
                        registry.register(wrapper)
                        if out_wrappers is not None:
                            out_wrappers[wrapper.name] = wrapper
                        registered += 1
                    except ValueError:
                        logger.debug(f"MCP prompt already registered, skipping")
            except Exception as exc:
                logger.debug(f"MCP server '{name}': prompts not supported: {exc}")

        logger.info(f"MCP server '{name}': connected ({transport_type}), registered {registered} capabilities")
        return stack
    except Exception as exc:
        logger.error(f"MCP server '{name}': tool discovery failed: {exc}")
        try:
            await stack.aclose()
        except Exception:
            pass
        return None


async def test_mcp_server(config: McpServerConfig) -> Dict[str, Any]:
    try:
        from mcp import ClientSession
    except ImportError:
        return {"success": False, "message": "mcp package not installed, run: pip install mcp"}

    transport_type = _infer_transport(config)
    if not transport_type:
        return {"success": False, "message": "no command or url configured"}

    resolved_command = None
    normalized_url = None
    connect_timeout = config.connect_timeout or 10

    # 传输级前置校验：给出与具体传输相关的精确错误消息
    if transport_type == "stdio":
        if not config.command:
            return {"success": False, "message": "stdio transport requires 'command'"}
        resolved_command, _, _ = _normalize_windows_stdio_command(
            config.command, config.args, config.env,
        )
    elif transport_type in ("sse", "streamable_http"):
        if not config.url:
            return {"success": False, "message": f"{transport_type} transport requires 'url'"}
        normalized_url = config.url

    stack = None
    try:
        stack, session = await _establish_mcp_session(
            "test", config, transport_type, connect_timeout
        )
        tools_result = await session.list_tools()
        tool_names = [t.name for t in tools_result.tools]
        return {
            "success": True,
            "message": f"Connected successfully ({transport_type}), found {len(tool_names)} tools: {', '.join(tool_names[:10])}",
            "resolved_command": resolved_command,
            "normalized_url": normalized_url,
        }
    except Exception as exc:
        # _establish_mcp_session 将观测到的 401/403 写入异常的 auth_codes
        codes = _extract_auth_status_codes(exc) | set(getattr(exc, "auth_codes", []))
        if codes & {401, 403}:
            message = f"认证被拒绝({sorted(codes)})，请检查 headers/env 凭证配置"
        else:
            message = f"Connection failed: {type(exc).__name__}: {exc}"
        logger.warning(f"MCP test connection failed: {message}")
        return {"success": False, "message": message}
    finally:
        if stack is not None:
            await stack.aclose()
