"""MCP Configuration Validators - 配置验证器

提供MCP配置的验证逻辑，确保配置的正确性和安全性。
"""

import os
import re
import shutil
from typing import List
from urllib.parse import urlparse

from backend.modules.config.schema import McpServerConfig


class McpConfigValidator:
    """MCP配置验证器"""

    # 允许的传输协议
    VALID_TRANSPORTS = {"stdio", "streamable_http", "sse"}

    # URL scheme白名单
    VALID_URL_SCHEMES = {"http", "https"}

    # 超时范围
    MIN_TIMEOUT = 5
    MAX_TIMEOUT = 300
    MIN_CONNECT_TIMEOUT = 5
    MAX_CONNECT_TIMEOUT = 60

    # 危险的命令模式
    DANGEROUS_COMMANDS = {
        "rm", "del", "format", "mkfs", "dd",
        "shutdown", "reboot", "halt",
        ">", ">>", "|", "&&", "||", ";",
    }

    def validate_server(self, config: McpServerConfig) -> List[str]:
        """验证服务器配置

        Args:
            config: 服务器配置

        Returns:
            错误列表，空列表表示验证通过
        """
        errors = []

        # 验证基本字段
        if not config.name or not config.name.strip():
            errors.append("Server name is required")

        if not config.id or not config.id.strip():
            errors.append("Server ID is required")

        # 验证传输协议
        if config.transport and config.transport not in self.VALID_TRANSPORTS:
            errors.append(
                f"Invalid transport '{config.transport}', "
                f"must be one of: {', '.join(self.VALID_TRANSPORTS)}"
            )

        # 验证超时参数
        if config.timeout < self.MIN_TIMEOUT or config.timeout > self.MAX_TIMEOUT:
            errors.append(
                f"Timeout must be between {self.MIN_TIMEOUT} and {self.MAX_TIMEOUT} seconds"
            )

        if config.connect_timeout < self.MIN_CONNECT_TIMEOUT or config.connect_timeout > self.MAX_CONNECT_TIMEOUT:
            errors.append(
                f"Connect timeout must be between {self.MIN_CONNECT_TIMEOUT} "
                f"and {self.MAX_CONNECT_TIMEOUT} seconds"
            )

        # 根据传输类型验证
        transport = config.transport or self._infer_transport(config)

        if transport == "stdio":
            errors.extend(self._validate_stdio_config(config))
        elif transport in ("streamable_http", "sse"):
            errors.extend(self._validate_http_config(config))
        else:
            errors.append("Cannot determine transport type: no command or url specified")

        # 验证工具过滤器
        errors.extend(self._validate_tool_filters(config))

        return errors

    def _infer_transport(self, config: McpServerConfig) -> str:
        """推断传输类型"""
        if config.command:
            return "stdio"
        if config.url:
            return "sse" if config.url.rstrip("/").endswith("/sse") else "streamable_http"
        return ""

    def _validate_stdio_config(self, config: McpServerConfig) -> List[str]:
        """验证stdio配置"""
        errors = []

        if not config.command:
            errors.append("stdio transport requires 'command'")
            return errors

        # 验证命令是否存在
        command = config.command.strip()
        if not command:
            errors.append("Command cannot be empty")
            return errors

        # 检查危险命令
        command_lower = command.lower()
        for dangerous in self.DANGEROUS_COMMANDS:
            if dangerous in command_lower:
                errors.append(
                    f"Command contains potentially dangerous pattern: '{dangerous}'"
                )

        # 验证命令是否可执行（仅在非Windows或.exe文件时）
        if os.name != "nt" or not command.lower().endswith((".exe", ".com")):
            # 检查是否在PATH中
            if not shutil.which(command.split()[0]):
                errors.append(
                    f"Command '{command.split()[0]}' not found in PATH. "
                    f"Please ensure it's installed and accessible."
                )

        # 验证参数
        if config.args:
            for arg in config.args:
                if not isinstance(arg, str):
                    errors.append(f"Invalid argument type: {type(arg).__name__}")
                # 检查危险参数
                arg_lower = arg.lower()
                for dangerous in self.DANGEROUS_COMMANDS:
                    if dangerous in arg_lower:
                        errors.append(
                            f"Argument contains potentially dangerous pattern: '{dangerous}'"
                        )

        # 验证环境变量
        if config.env:
            for key, value in config.env.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    errors.append(f"Invalid env variable: {key}={value}")
                if not key.strip():
                    errors.append("Environment variable name cannot be empty")

        return errors

    def _validate_http_config(self, config: McpServerConfig) -> List[str]:
        """验证HTTP/SSE配置"""
        errors = []

        if not config.url:
            errors.append("HTTP/SSE transport requires 'url'")
            return errors

        # 验证URL格式
        try:
            parsed = urlparse(config.url)

            if not parsed.scheme:
                errors.append("URL must include scheme (http:// or https://)")
            elif parsed.scheme not in self.VALID_URL_SCHEMES:
                errors.append(
                    f"Invalid URL scheme '{parsed.scheme}', "
                    f"must be one of: {', '.join(self.VALID_URL_SCHEMES)}"
                )

            if not parsed.netloc:
                errors.append("URL must include host")

            # 安全检查：警告使用http而非https
            if parsed.scheme == "http" and not parsed.hostname in ("localhost", "127.0.0.1", "::1"):
                errors.append(
                    "Warning: Using unencrypted HTTP for remote server. "
                    "Consider using HTTPS for security."
                )

        except Exception as e:
            errors.append(f"Invalid URL format: {e}")

        # 验证headers
        if config.headers:
            for key, value in config.headers.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    errors.append(f"Invalid header: {key}={value}")
                if not key.strip():
                    errors.append("Header name cannot be empty")

                # 检查敏感信息泄露
                key_lower = key.lower()
                if key_lower in ("authorization", "api-key", "x-api-key"):
                    if value and len(value) < 10:
                        errors.append(
                            f"Header '{key}' appears to contain a short token. "
                            f"Ensure it's correct."
                        )

        return errors

    def _validate_tool_filters(self, config: McpServerConfig) -> List[str]:
        """验证工具过滤器"""
        errors = []

        # 验证include_tools
        if config.include_tools:
            if not isinstance(config.include_tools, list):
                errors.append("include_tools must be a list")
            else:
                for tool in config.include_tools:
                    if not isinstance(tool, str):
                        errors.append(f"Invalid tool name in include_tools: {tool}")
                    elif tool != "*" and not self._is_valid_tool_name(tool):
                        errors.append(
                            f"Invalid tool name pattern in include_tools: '{tool}'"
                        )

        # 验证exclude_tools
        if config.exclude_tools:
            if not isinstance(config.exclude_tools, list):
                errors.append("exclude_tools must be a list")
            else:
                for tool in config.exclude_tools:
                    if not isinstance(tool, str):
                        errors.append(f"Invalid tool name in exclude_tools: {tool}")
                    elif not self._is_valid_tool_name(tool):
                        errors.append(
                            f"Invalid tool name pattern in exclude_tools: '{tool}'"
                        )

        # 检查冲突
        if config.include_tools and config.exclude_tools:
            include_set = set(config.include_tools)
            exclude_set = set(config.exclude_tools)
            conflicts = include_set & exclude_set
            if conflicts:
                errors.append(
                    f"Tool names appear in both include and exclude: {conflicts}"
                )

        return errors

    def _is_valid_tool_name(self, name: str) -> bool:
        """验证工具名称格式

        工具名称应该是有效的标识符或通配符
        """
        if name == "*":
            return True

        # 允许字母、数字、下划线、连字符
        pattern = r'^[a-zA-Z0-9_-]+$'
        return bool(re.match(pattern, name))

    def validate_registry(self, servers: List[McpServerConfig]) -> List[str]:
        """验证整个注册表

        Args:
            servers: 服务器配置列表

        Returns:
            错误列表
        """
        errors = []

        # 检查重复的ID和名称
        ids = []
        names = []

        for i, server in enumerate(servers):
            # 验证单个服务器
            server_errors = self.validate_server(server)
            if server_errors:
                errors.append(f"Server #{i+1} ({server.name or server.id}): {', '.join(server_errors)}")

            # 检查重复
            if server.id in ids:
                errors.append(f"Duplicate server ID: '{server.id}'")
            ids.append(server.id)

            if server.name in names:
                errors.append(f"Duplicate server name: '{server.name}'")
            names.append(server.name)

        return errors
