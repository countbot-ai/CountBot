"""Shell 命令执行工具

提供安全的 Shell 命令执行功能：
- 安全检查（危险命令拦截、路径限制）
- 超时控制和输出截断
- 跨平台字符编码自动检测
"""

import asyncio
import locale
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from backend.modules.tools.base import Tool


DANGEROUS_PATTERNS = [
    r"\brm\s+-[rf]{1,2}\b",
    r"\bdel\s+/[fq]\b",
    r"\brmdir\s+/s\b",
    r"^(format|mkfs|diskpart)\b",
    r"\bdd\s+if=",
    r">\s*/dev/sd",
    r"\b(shutdown|reboot|poweroff|halt)\b",
    r":\(\)\s*\{.*\};\s*:",
    r"\binit\s+[06]\b",
]


def is_dangerous_command(command: str) -> bool:
    """检测命令是否匹配危险模式
    
    Args:
        command: 待检测的命令
        
    Returns:
        bool: 是否为危险命令
    """
    command_lower = command.lower()
    
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command_lower):
            logger.warning(f"检测到危险命令模式: {pattern}")
            return True
    
    return False


class ExecTool(Tool):
    """Shell 命令执行工具
    
    在工作空间中安全执行 Shell 命令，支持超时控制、输出截断和自动编码检测。
    """

    def __init__(
        self,
        workspace: Path,
        timeout: int = 30,
        max_output_length: int = 10000,
        allow_dangerous: bool = False,
        deny_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        restrict_to_workspace: bool = True,
    ):
        """初始化 Shell 执行工具
        
        Args:
            workspace: 工作空间根目录
            timeout: 超时时间（秒），默认 30
            max_output_length: 最大输出长度（字符），默认 10000
            allow_dangerous: 是否允许危险命令，默认 False
            deny_patterns: 自定义拒绝模式，默认使用 DANGEROUS_PATTERNS
            allow_patterns: 允许模式（白名单），设置后仅允许匹配的命令
            restrict_to_workspace: 是否限制在工作空间内，默认 True
        """
        self.workspace = workspace.resolve()
        self.timeout = timeout
        self.max_output_length = max_output_length
        self.allow_dangerous = allow_dangerous
        self.deny_patterns = deny_patterns or DANGEROUS_PATTERNS
        self.allow_patterns = allow_patterns or []
        self.restrict_to_workspace = restrict_to_workspace
        
        logger.debug(
            f"ExecTool initialized: workspace={self.workspace}, "
            f"timeout={timeout}s, max_output={max_output_length}, "
            f"allow_dangerous={allow_dangerous}, restrict_to_workspace={restrict_to_workspace}"
        )

    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        return "在工作空间中执行 Shell 命令，返回 stdout 和 stderr 合并输出，默认阻止危险命令"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Optional working directory for the command (relative to workspace)",
                },
            },
            "required": ["command"],
        }

    async def execute(self, **kwargs: Any) -> str:
        """执行 Shell 命令
        
        Args:
            **kwargs: 命令参数
                - command (str): 要执行的命令（必需）
                - working_dir (str): 工作目录，相对于工作空间（可选）
            
        Returns:
            str: 命令输出或错误信息
        """
        command = kwargs.get("command", "")
        working_dir = kwargs.get("working_dir")
        
        if not command:
            return "Error: Command parameter is required"
        
        # 解析工作目录
        if working_dir:
            try:
                cwd = (self.workspace / working_dir).resolve()
                if not str(cwd).startswith(str(self.workspace)):
                    return f"Error: Working directory outside workspace: {working_dir}"
            except Exception as e:
                return f"Error: Invalid working directory: {e}"
        else:
            cwd = self.workspace
        
        # 安全检查
        guard_error = self._guard_command(command, str(cwd))
        if guard_error:
            return guard_error
        
        try:
            logger.info(f"执行命令: {command} (cwd: {cwd})")
            
            # 创建子进程
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
            )
            
            # 等待完成（带超时）
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                error_msg = f"Error: Command timed out after {self.timeout} seconds"
                logger.error(error_msg)
                return error_msg
            
            # 构建输出
            output_parts = []
            
            if stdout:
                decoded_stdout = self._decode_output(stdout)
                # 统一换行符格式
                decoded_stdout = decoded_stdout.replace('\r\n', '\n').replace('\r', '\n')
                output_parts.append(decoded_stdout)
            
            if stderr:
                decoded_stderr = self._decode_output(stderr)
                decoded_stderr = decoded_stderr.replace('\r\n', '\n').replace('\r', '\n')
                if decoded_stderr.strip():
                    output_parts.append(f"STDERR:\n{decoded_stderr}")
            
            if process.returncode != 0:
                output_parts.append(f"\nExit code: {process.returncode}")
            
            result = "\n".join(output_parts) if output_parts else "(no output)"
            
            # 截断过长输出
            if len(result) > self.max_output_length:
                truncated_chars = len(result) - self.max_output_length
                result = (
                    result[: self.max_output_length]
                    + f"\n... (输出已截断，还有 {truncated_chars} 个字符)"
                )
                logger.warning(f"输出已截断至 {self.max_output_length} 字符")
            
            if process.returncode == 0:
                logger.info("命令执行成功")
            else:
                logger.warning(f"命令退出码: {process.returncode}")
            
            return result
            
        except Exception as e:
            logger.error(f"执行命令时发生异常: {e}")
            return f"Error executing command: {str(e)}"

    def _decode_output(self, output: bytes) -> str:
        """解码命令输出，自动检测字符编码
        
        尝试多种编码以确保跨平台字符正确显示（特别是中文等非 ASCII 字符）。
        编码优先级：系统默认 > GBK > GB2312 > CP936 > UTF-8 > UTF-8(replace)
        
        Args:
            output: 待解码的字节数据
            
        Returns:
            str: 解码后的字符串
        """
        system_encoding = locale.getpreferredencoding() or 'utf-8'
        
        encodings_to_try = [
            system_encoding,
            'gbk',
            'gb2312',
            'cp936',
            'utf-8',
        ]
        
        # 去重保持顺序
        seen = set()
        unique_encodings = []
        for enc in encodings_to_try:
            if enc not in seen:
                seen.add(enc)
                unique_encodings.append(enc)
        
        # 尝试每种编码
        for encoding in unique_encodings:
            try:
                decoded = output.decode(encoding)
                logger.debug(f"使用编码解码成功: {encoding}")
                return decoded
            except (UnicodeDecodeError, LookupError):
                continue
        
        # 所有编码失败，使用 replace 模式
        logger.warning(f"所有编码尝试失败，使用 UTF-8 replace 模式。已尝试: {unique_encodings}")
        return output.decode('utf-8', errors='replace')

    def _guard_command(self, command: str, cwd: str) -> str | None:
        """命令安全检查
        
        执行安全策略验证：白名单检查、危险模式检测、路径遍历检测、工作空间边界检查
        
        Args:
            command: 待检查的命令
            cwd: 工作目录路径
            
        Returns:
            str | None: 如果命令被阻止返回错误信息，否则返回 None
        """
        cmd = command.strip()
        lower = cmd.lower()
        
        # 白名单检查
        if self.allow_patterns:
            if not any(re.search(p, lower) for p in self.allow_patterns):
                return "Error: Command blocked by safety guard (not in allowlist)"
        
        # 危险模式检查
        if not self.allow_dangerous:
            for pattern in self.deny_patterns:
                if re.search(pattern, lower):
                    return "Error: Command blocked by safety guard (dangerous pattern detected)"
        
        # 工作空间路径限制
        if self.restrict_to_workspace:
            # 路径遍历检查
            if "..\\" in cmd or "../" in cmd:
                return "Error: Command blocked by safety guard (path traversal detected)"
            
            cwd_path = Path(cwd).resolve()
            
            # 提取命令中的路径（排除 URL）
            # 先移除 URL 避免误判
            cmd_without_urls = re.sub(r'https?://[^\s"\']+', '', cmd)
            
            # Windows 绝对路径：C:\path\to\file
            win_paths = re.findall(r"[A-Za-z]:\\[^\s\"']+", cmd_without_urls)
            
            # POSIX 绝对路径：以 / 开头且在空格/引号前，但排除相对路径中的斜杠
            # 只匹配命令开头或空格后的 /path 格式
            posix_paths = re.findall(r'(?:^|\s)(/[^\s"\']+)', cmd_without_urls)
            
            # 相对路径：./ 或 ~/
            relative_paths = re.findall(r"(?:\.\/|~\/)[^\s\"']+", cmd_without_urls)
            
            all_paths = win_paths + posix_paths + relative_paths
            
            for raw in all_paths:
                try:
                    p = Path(raw).resolve()
                    # 如果路径不存在，尝试父目录
                    if not p.exists():
                        # 可能是相对路径，尝试相对于 cwd 解析
                        p = (cwd_path / raw).resolve()
                        if not p.exists():
                            p = p.parent
                except Exception:
                    continue
                
                # 验证路径在工作空间内
                try:
                    p.relative_to(cwd_path)
                except ValueError:
                    # 检查是否在工作空间内（使用 workspace 而不是 cwd）
                    try:
                        p.relative_to(self.workspace)
                    except ValueError:
                        return f"Error: Command blocked by safety guard (path outside working dir: {raw})"
        
        return None


class ExecToolSafe(ExecTool):
    """安全模式 Shell 执行工具
    
    预配置严格安全策略：阻止危险命令、30秒超时、强制工作空间限制
    """

    def __init__(self, workspace: Path):
        """初始化安全模式 Shell 执行工具
        
        Args:
            workspace: 工作空间根目录
        """
        super().__init__(
            workspace=workspace,
            timeout=30,
            max_output_length=10000,
            allow_dangerous=False,
            restrict_to_workspace=True,
        )
        logger.info("ExecToolSafe 初始化完成，已启用严格安全策略")
