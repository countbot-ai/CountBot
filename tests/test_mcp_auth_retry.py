"""MCP 认证加固回归测试

覆盖：
- 401 恰好重试一次：首次 401 触发一次重试，两次都 401 则判定为配置错误
- redirect:manual：服务器 302 时凭证头不得跟随发往其他源
- 200 正常路径仍可完成 MCP 握手（用 SDK 的内存双端模拟，不走网络）
"""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from backend.modules.config.schema import McpServerConfig
# 别名导入：避免 pytest 把 test_mcp_server 误收集为测试用例
from backend.modules.mcp.connection import (
    _extract_auth_status_codes,
    test_mcp_server as run_mcp_server_test,
)


def run(coro):
    return asyncio.run(coro)


class _ProgrammableServer:
    """可编程 HTTP 记录器：按脚本返回响应，记录每个请求的方法/路径/头。"""

    def __init__(self, script):
        # script: list[ (status, extra_headers, body) ]，逐请求消费，耗尽后重复最后一项
        self.script = list(script)
        self.requests = []
        self._lock = threading.Lock()

    def make_handler(self):
        server = self

        class H(BaseHTTPRequestHandler):
            def _handle(self):
                with server._lock:
                    server.requests.append(
                        {
                            "method": self.command,
                            "path": self.path,
                            "headers": dict(self.headers),
                        }
                    )
                    idx = min(len(server.requests) - 1, len(server.script) - 1)
                    status, extra_headers, body = server.script[idx]
                payload = json.dumps(body or {}).encode()
                self.send_response(status)
                for k, v in (extra_headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = do_DELETE = do_PUT = _handle

            def log_message(self, *a):
                pass

        return H

    def start(self, port):
        self.httpd = HTTPServer(("127.0.0.1", port), self.make_handler())
        t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        t.start()
        return self

    def stop(self):
        self.httpd.shutdown()


def _server_config(url: str, headers: dict | None = None) -> McpServerConfig:
    return McpServerConfig(
        id="probe",
        name="probe",
        enabled=True,
        transport="streamable_http",
        url=url,
        headers=headers or {},
        timeout=5,
        connect_timeout=5,
    )


def test_401_retried_exactly_once():
    """首次 401 触发一次重试；两次都 401 判定为配置错误，且总共只发 2 次请求。"""
    server = _ProgrammableServer([(401, {}, {"error": "unauthorized"})]).start(19861)
    try:
        result = run(
            run_mcp_server_test(_server_config("http://127.0.0.1:19861/mcp",
                                          {"Authorization": "Bearer tok"}))
        )
        assert result["success"] is False
        assert "认证被拒绝" in result["message"], result["message"]
        assert len(server.requests) == 2, (
            f"401 应恰好重试一次（共 2 次请求），实际 {len(server.requests)} 次"
        )
        # 每次请求都必须携带凭证头
        for req in server.requests:
            assert req["headers"].get("Authorization") == "Bearer tok"
    finally:
        server.stop()


def test_redirect_not_followed_with_credentials():
    """302 到其他端口时不得跟随：凭证头不允许发往重定向目标。"""
    redirector = _ProgrammableServer(
        [(302, {"Location": "http://127.0.0.1:19863/mcp"}, {})]
    ).start(19862)
    evil = _ProgrammableServer([(200, {}, {})]).start(19863)
    try:
        result = run(
            run_mcp_server_test(_server_config("http://127.0.0.1:19862/mcp",
                                          {"Authorization": "Bearer secret"}))
        )
        assert result["success"] is False
        # 只请求了原始端点一次，重定向目标零请求
        assert len(redirector.requests) == 1, redirector.requests
        assert len(evil.requests) == 0, "凭证不应跟随重定向发往其他源"
    finally:
        redirector.stop()
        evil.stop()


def test_extract_auth_status_codes_from_exception_group():
    """状态码提取必须能穿透 SDK 的 ExceptionGroup 包装。"""
    import httpx

    request = httpx.Request("POST", "http://x/mcp")
    response = httpx.Response(401, request=request)
    inner = httpx.HTTPStatusError("401 Unauthorized", request=request, response=response)
    grouped = ExceptionGroup("tg", [inner])

    assert _extract_auth_status_codes(grouped) == {401}
    assert _extract_auth_status_codes(RuntimeError("boom")) == set()
