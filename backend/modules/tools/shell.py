"""Shell 命令执行工具

提供安全的 Shell 命令执行功能：
- 安全检查（危险命令拦截、路径限制）
- 超时控制和输出截断
- 跨平台字符编码自动检测
"""

import json
import asyncio
import contextvars
import locale
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from backend.modules.tools.base import Tool
from backend.modules.tools.command_guard import DANGEROUS_PATTERNS, guard_command
from backend.modules.tools._failure import format_failure, single_line
from backend.modules.tools.execution import ErrorCategory, RetrySafety, SideEffectState, ToolResult
from backend.modules.tools._path_resolver import resolve_path
from backend.modules.tools.monitoring import (
    MONITOR_PARAMETER_SCHEMA,
    build_default_monitor_config,
    parse_monitor_config,
    run_with_monitoring,
)


class ExecTool(Tool):
    """Shell 命令执行工具
    
    在工作空间中安全执行 Shell 命令，支持超时控制、输出截断和自动编码检测。
    """

    def __init__(
        self,
        workspace: Path,
        timeout: int = 180,
        max_output_length: int = 10000,
        allow_dangerous: bool = False,
        deny_patterns: Optional[List[str]] = None,
        allow_patterns: Optional[List[str]] = None,
        restrict_to_workspace: bool = True,
    ):
        """初始化 Shell 执行工具
        
        Args:
            workspace: 工作空间根目录
            timeout: 超时时间（秒），默认 180
            max_output_length: 最大输出长度（字符），默认 10000
            allow_dangerous: 是否允许危险命令，默认 False
            deny_patterns: 自定义拒绝模式，默认使用 DANGEROUS_PATTERNS
            allow_patterns: 允许模式（白名单），设置后仅允许匹配的命令
            restrict_to_workspace: 是否限制在工作空间内，默认 True
        """
        normalized_deny_patterns = [
            str(pattern).strip()
            for pattern in (deny_patterns or DANGEROUS_PATTERNS)
            if str(pattern or "").strip()
        ]
        normalized_allow_patterns = (
            [
                str(pattern).strip()
                for pattern in allow_patterns
                if str(pattern or "").strip()
            ]
            if allow_patterns is not None
            else None
        )

        # 初始工作空间快照（用于日志与兜底）；运行时解析统一走 resolve_path /
        # workspace property，跟随配置热切换，不冻结构造时的路径基准。
        self._workspace = workspace.resolve()
        self.timeout = timeout
        self.max_output_length = max_output_length
        self.allow_dangerous = allow_dangerous
        self.deny_patterns = normalized_deny_patterns
        self.allow_patterns = normalized_allow_patterns
        self.restrict_to_workspace = restrict_to_workspace
        
        logger.debug(
            f"ExecTool initialized: workspace={self._workspace}, "
            f"timeout={timeout}s, max_output={max_output_length}, "
            f"allow_dangerous={allow_dangerous}, restrict_to_workspace={restrict_to_workspace}"
        )
        # 消息上下文用 contextvar 存储，保证并发会话隔离：
        # 工具实例被渠道 handler 的所有并发消息共享，实例属性会互相覆盖，
        # 导致子进程环境变量（渠道/发件人/账号）串到其它会话。
        self._message_context_ctx: contextvars.ContextVar[Optional[Dict[str, Any]]] = (
            contextvars.ContextVar("exec_tool_message_context", default=None)
        )
        # 当前执行中的子进程，供取消回调终止。同样用 contextvar：
        # 实例属性会让并发会话的取消互相误杀对方的进程。
        self._active_process_ctx: contextvars.ContextVar[Optional[Any]] = (
            contextvars.ContextVar("exec_tool_active_process", default=None)
        )
        # 取消令牌同样用 contextvar 按会话隔离，避免并发会话的
        # 取消相互误杀。
        self._cancel_token_ctx: contextvars.ContextVar[Optional[Any]] = (
            contextvars.ContextVar("exec_tool_cancel_token", default=None)
        )

    def set_cancel_token(self, token) -> None:
        """登记取消令牌。

        令牌的 cancel 回调在取消发生时同步触发，此处只负责记住它；
        真正的进程终止在每个命令执行期间注册与注销。
        使用 contextvar 保证并发会话的令牌相互隔离（与 registry 的
        set_session_id 同理）。
        """
        self._cancel_token_ctx.set(token)

    @property
    def workspace(self) -> Path:
        """当前工作空间（跟随运行期热切换，不冻结构造时快照）。

        相对命令的 cwd / 危险命令校验 / 产出物路径检查均以此为基准；
        与 filesystem 工具动态读 config 的行为保持一致。
        """
        return resolve_path(".")

    @property
    def _message_context(self) -> Optional[Dict[str, Any]]:
        return self._message_context_ctx.get()

    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        return (
            "Run a shell command. For long-running foreground commands, set `timeout` "
            "and `monitor` to emit periodic progress updates. If you need live in-chat "
            "progress, keep the command in the foreground; detached commands launched "
            "with `nohup`, `tmux -d`, or trailing `&` return immediately and will not "
            "emit sustained tool progress."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command.",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Working directory.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Optional timeout in seconds for this command.",
                    "minimum": 10,
                    "maximum": 3600,
                },
                "monitor": MONITOR_PARAMETER_SCHEMA,
            },
            "required": ["command"],
            "additionalProperties": False,
        }

    def set_message_context(self, message_context: Optional[Dict[str, Any]]) -> None:
        """保存当前消息上下文，供技能脚本读取渠道环境变量（异步安全）。"""
        self._message_context_ctx.set(message_context or None)

    def _json_safe_metadata(self, value: Any) -> Any:
        """将 metadata 递归裁剪为可 JSON 序列化的结构。"""
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            result: Dict[str, Any] = {}
            for key, item in value.items():
                if callable(item):
                    continue
                safe_item = self._json_safe_metadata(item)
                if safe_item is not None:
                    result[str(key)] = safe_item
            return result
        if isinstance(value, (list, tuple, set)):
            result = []
            for item in value:
                if callable(item):
                    continue
                safe_item = self._json_safe_metadata(item)
                if safe_item is not None:
                    result.append(safe_item)
            return result
        return str(value)

    def _build_subprocess_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        context = self._message_context or {}
        metadata = context.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}

        # 设置运行时 python 环境变量，确保执行 "python xxx" 命令时默认在运行时环境执行
        # 获取当前运行的 python.exe 绝对路径及其所在目录
        python_exe = Path(sys.executable).resolve()
        python_dir = python_exe.parent
        
        # 初始 PATH 列表：首先包含 python.exe 所在的目录
        new_path_entries = [str(python_dir)]
        
        # 针对 Windows 的特殊处理
        if os.name == 'nt':
            # 情况 A: 如果 python.exe 在根目录（如 Conda），则需要添加 Scripts 子目录
            # 情况 B: 如果 python.exe 已经在 Scripts 目录（如 venv），则无需重复添加
            if python_dir.name.lower() != "scripts":
                scripts_dir = python_dir / "Scripts"
                if scripts_dir.exists():
                    new_path_entries.insert(0, str(scripts_dir))
        else:
            # Unix-like 系统 (Linux/macOS): 
            # Python 和脚本通常都在 bin 目录下，python_dir 已经覆盖了
            pass

        # 获取系统现有的 PATH
        path_key = "PATH" if "PATH" in env else "Path"
        current_path = env.get(path_key, "")
        
        # 合并路径：新探测的路径置于最前面
        new_path_entries.append(current_path)
        env[path_key] = os.pathsep.join(filter(None, new_path_entries))

        def set_env(name: str, value: Any) -> None:
            text = str(value or "").strip()
            if text:
                env[name] = text

        set_env("COUNTBOT_CHANNEL", context.get("channel"))
        set_env("COUNTBOT_CHAT_ID", context.get("chat_id"))
        set_env("COUNTBOT_SENDER_ID", context.get("sender_id"))
        set_env(
            "COUNTBOT_ACCOUNT_ID",
            metadata.get("account_id")
            or metadata.get("reply_account_id")
            or metadata.get("context_owner_account_id"),
        )
        set_env("COUNTBOT_SOURCE_ACCOUNT_ID", metadata.get("source_account_id"))
        set_env("COUNTBOT_REPLY_ACCOUNT_ID", metadata.get("reply_account_id"))
        set_env("COUNTBOT_CONTEXT_OWNER_ACCOUNT_ID", metadata.get("context_owner_account_id"))
        set_env("COUNTBOT_SESSION_SCOPE", metadata.get("session_scope"))
        if metadata:
            env["COUNTBOT_MESSAGE_METADATA"] = json.dumps(
                self._json_safe_metadata(metadata),
                ensure_ascii=False,
            )
        return env

    @staticmethod
    def _normalize_output_text(text: str) -> str:
        return text.replace('\r\n', '\n').replace('\r', '\n')

    def _append_preview_lines(
        self,
        preview_lines: List[str],
        output: bytes,
        limit: int = 40,
    ) -> None:
        decoded = self._normalize_output_text(self._decode_output(output))
        lines = decoded.split('\n')
        preview_lines.extend(lines)
        if len(preview_lines) > limit:
            del preview_lines[:-limit]

    async def _collect_process_output(
        self,
        process: asyncio.subprocess.Process,
        timeout: int,
        stdout_preview_lines: List[str],
        stderr_preview_lines: List[str],
    ) -> tuple[bytes, bytes]:
        stdout_buffer = bytearray()
        stderr_buffer = bytearray()

        async def read_stream(
            stream: Optional[asyncio.StreamReader],
            buffer: bytearray,
            preview_lines: List[str],
        ) -> None:
            if stream is None:
                return

            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    break
                buffer.extend(chunk)
                self._append_preview_lines(preview_lines, chunk)

        stdout_task = asyncio.create_task(
            read_stream(process.stdout, stdout_buffer, stdout_preview_lines)
        )
        stderr_task = asyncio.create_task(
            read_stream(process.stderr, stderr_buffer, stderr_preview_lines)
        )

        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            raise

        await asyncio.gather(stdout_task, stderr_task)
        return bytes(stdout_buffer), bytes(stderr_buffer)

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
        requested_timeout = kwargs.get("timeout")
        
        if not command:
            return "Error: Command parameter is required"

        try:
            monitor = parse_monitor_config(kwargs.get("monitor"))
        except ValueError as e:
            return f"Error: {e}"

        timeout = self.timeout
        if requested_timeout is not None:
            try:
                timeout = int(requested_timeout)
            except (TypeError, ValueError):
                return "Error: timeout must be an integer"
            if timeout <= 0:
                return "Error: timeout must be greater than 0"
        
        if monitor is None:
            monitor = build_default_monitor_config(
                tool_name=self.name,
                timeout_sec=timeout,
                command=command,
            )
            if monitor is not None:
                logger.info(
                    "Auto-enabled monitor for exec: expected={}s notify_every={}s",
                    monitor.expected_duration_sec,
                    monitor.notify_every_sec,
                )
        
        # 解析工作目录
        if working_dir:
            try:
                cwd = (self.workspace / working_dir).resolve()
                if not str(cwd).startswith(str(self.workspace)):
                    return f"Error: Working directory outside workspace: {working_dir}"
            except Exception as e:
                return f"Error: Invalid working directory: {e}"
        else:
            # 默认使用 workspace 作为工作目录
            # 这确保了即使用户配置了自定义 workspace 路径，命令也在正确的目录执行
            cwd = self.workspace
        
        # 安全检查
        guard_error = self._guard_command(command, str(cwd))
        if guard_error:
            return guard_error
        
        try:
            logger.info(f"执行命令: {command} (cwd: {cwd})")
            stdout_preview_lines: List[str] = []
            stderr_preview_lines: List[str] = []

            def build_output_progress_details() -> Optional[Dict[str, Any]]:
                details: Dict[str, Any] = {}

                latest_stdout_preview = "\n".join(stdout_preview_lines[-12:]).strip()
                latest_stderr_preview = "\n".join(stderr_preview_lines[-12:]).strip()

                if latest_stdout_preview:
                    details["latest_output_preview"] = latest_stdout_preview
                if latest_stderr_preview:
                    details["latest_stderr_preview"] = latest_stderr_preview

                return details or None
            
            # 创建子进程
            try:
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(cwd),
                    env=self._build_subprocess_env(),
                    # 独立进程组：取消时能连同 shell 派生的子进程一起终止
                    start_new_session=True,
                )
            except NotImplementedError as e:
                error_msg = f"Error: Subprocess not supported on this platform: {str(e)}"
                logger.error(error_msg)
                return error_msg
            except PermissionError as e:
                error_msg = f"Error: Permission denied: {str(e)}"
                logger.error(error_msg)
                return error_msg
            except OSError as e:
                error_msg = f"Error: Failed to create subprocess: {str(e)}"
                logger.error(error_msg)
                return error_msg
            
            # 等待完成（带超时）
            unregister_cancel = self._register_cancel_hook(process)
            try:
                stdout, stderr = await run_with_monitoring(
                    self._collect_process_output(
                        process=process,
                        timeout=timeout,
                        stdout_preview_lines=stdout_preview_lines,
                        stderr_preview_lines=stderr_preview_lines,
                    ),
                    monitor,
                    details_provider=build_output_progress_details,
                )
            except asyncio.TimeoutError:
                if unregister_cancel is not None:
                    unregister_cancel()
                error_msg = f"Error: Command timed out after {timeout} seconds"
                latest_preview = build_output_progress_details() or {}
                preview_parts: List[str] = [error_msg]
                if latest_preview.get("latest_output_preview"):
                    preview_parts.append(
                        "Latest captured stdout:\n"
                        f"{latest_preview['latest_output_preview']}"
                    )
                if latest_preview.get("latest_stderr_preview"):
                    preview_parts.append(
                        "Latest captured stderr:\n"
                        f"{latest_preview['latest_stderr_preview']}"
                    )
                error_msg = "\n\n".join(preview_parts)
                logger.error(error_msg)
                return error_msg
            
            # 构建输出
            output_parts = []
            
            if stdout:
                decoded_stdout = self._decode_output(stdout)
                # 统一换行符格式
                decoded_stdout = self._normalize_output_text(decoded_stdout)
                output_parts.append(decoded_stdout)
            
            if stderr:
                decoded_stderr = self._decode_output(stderr)
                decoded_stderr = self._normalize_output_text(decoded_stderr)
                if decoded_stderr.strip():
                    output_parts.append(f"STDERR:\n{decoded_stderr}")
            
            if process.returncode != 0:
                output_parts.insert(0, f"COMMAND FAILED (exit code {process.returncode})\n")
                output_parts.append(f"\nExit code: {process.returncode}")
            
            result = "\n".join(output_parts) if output_parts else "(no output)"
            
            # 截断过长输出：完整内容落盘，模型可后续按需读取
            if len(result) > self.max_output_length:
                result = self._truncate_with_artifact(result, command=single_line(command))
                logger.warning(f"输出已截断至 {self.max_output_length} 字符")
            
            if process.returncode == 0:
                logger.info("命令执行成功")
            else:
                logger.warning(f"命令退出码: {process.returncode}")

            if unregister_cancel is not None:
                unregister_cancel()
            return result
            
        except Exception as e:
            detail = f"执行命令时发生异常: {e}"
            logger.error(detail)
            return format_failure(
                kind="execution_error",
                summary=f"Command execution failed: {single_line(e)}",
                next="check the command and environment, then retry",
                detail=detail,
            )

    async def execute_outcome(self, **kwargs: Any) -> ToolResult:
        command = kwargs.get("command", "")
        working_dir = kwargs.get("working_dir")
        requested_timeout = kwargs.get("timeout")
        no_effect = {"retry_safety": RetrySafety.UNSAFE, "side_effect_state": SideEffectState.NOT_ATTEMPTED}
        if not command:
            return ToolResult.failure(ErrorCategory.VALIDATION, "Error: Command parameter is required", **no_effect)
        try:
            monitor = parse_monitor_config(kwargs.get("monitor"))
        except ValueError as exc:
            return ToolResult.failure(ErrorCategory.VALIDATION, f"Error: {exc}", **no_effect)
        timeout = self.timeout
        if requested_timeout is not None:
            try:
                timeout = int(requested_timeout)
            except (TypeError, ValueError):
                return ToolResult.failure(ErrorCategory.VALIDATION, "Error: timeout must be an integer", **no_effect)
            if timeout <= 0:
                return ToolResult.failure(ErrorCategory.VALIDATION, "Error: timeout must be greater than 0", **no_effect)
        if monitor is None:
            monitor = build_default_monitor_config(tool_name=self.name, timeout_sec=timeout, command=command)
        if working_dir:
            try:
                cwd = (self.workspace / working_dir).resolve()
                if not str(cwd).startswith(str(self.workspace)):
                    return ToolResult.failure(ErrorCategory.PERMISSION, f"Error: Working directory outside workspace: {working_dir}", **no_effect)
            except Exception as exc:
                return ToolResult.failure(ErrorCategory.VALIDATION, f"Error: Invalid working directory: {exc}", **no_effect)
        else:
            cwd = self.workspace
        guard_error = self._guard_command(command, str(cwd))
        if guard_error:
            return ToolResult.failure(ErrorCategory.PERMISSION, guard_error, **no_effect)
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
                env=self._build_subprocess_env(),
                # 独立进程组：取消时连同派生子进程一起终止
                start_new_session=True,
            )
        except PermissionError as exc:
            return ToolResult.failure(ErrorCategory.PERMISSION, f"Error: Permission denied: {exc}", **no_effect)
        except (NotImplementedError, OSError) as exc:
            return ToolResult.failure(ErrorCategory.EXECUTION, f"Error: Failed to create subprocess: {exc}", **no_effect)
        unregister_cancel = self._register_cancel_hook(process)
        try:
            try:
                stdout, stderr = await run_with_monitoring(
                    self._collect_process_output(process=process, timeout=timeout, stdout_preview_lines=[], stderr_preview_lines=[]),
                    monitor,
                    details_provider=lambda: None,
                )
            except asyncio.TimeoutError:
                return ToolResult.unknown_outcome(ErrorCategory.TIMEOUT, f"Error: Command timed out after {timeout} seconds", retryable=True, retry_safety=RetrySafety.UNSAFE)
            except Exception as exc:
                return ToolResult.unknown_outcome(
                    ErrorCategory.EXECUTION,
                    format_failure(kind="execution_error", summary=f"Command execution failed: {single_line(exc)}", next="check the command and environment, then retry", detail=f"执行命令时发生异常: {exc}"),
                    retry_safety=RetrySafety.UNSAFE,
                )
            output_parts: List[str] = []
            if stdout:
                output_parts.append(self._normalize_output_text(self._decode_output(stdout)))
            if stderr:
                decoded_stderr = self._normalize_output_text(self._decode_output(stderr))
                if decoded_stderr.strip():
                    output_parts.append(f"STDERR:\n{decoded_stderr}")
            if process.returncode != 0:
                output_parts.insert(0, f"COMMAND FAILED (exit code {process.returncode})\n")
                output_parts.append(f"\nExit code: {process.returncode}")
            result = "\n".join(output_parts) if output_parts else "(no output)"
            if len(result) > self.max_output_length:
                result = self._truncate_with_artifact(result, command=single_line(command))
            if process.returncode != 0:
                return ToolResult.unknown_outcome(ErrorCategory.EXECUTION, result, retry_safety=RetrySafety.UNSAFE)
            return ToolResult.success(result, retry_safety=RetrySafety.UNSAFE, side_effect_state=SideEffectState.COMMITTED)
        finally:
            if unregister_cancel is not None:
                unregister_cancel()

    # 截断时头部保留比例。命令失败原因（异常栈、编译错误汇总）通常位于输出末尾，
    # 而开头的提示信息同样有价值，故按小头部 + 大尾部保留，而非仅保留头部。
    HEAD_KEEP_RATIO = 0.25

    def _truncate_with_artifact(self, result: str, *, command: str = "") -> str:
        """截断超长输出，并把完整内容落到临时文件。

        保留少量开头与较多结尾：构建/测试失败的原因几乎总在末尾，只保头部会让
        模型看不到真正的错误行。完整输出写入 ``temp/`` 并给出路径，可按需回读。

        Args:
            result: 完整输出文本
            command: 触发本次输出的命令，写入文件头部便于回溯

        Returns:
            适合放进上下文的截断文本
        """
        if len(result) <= self.max_output_length:
            return result

        total = len(result)
        head_len = int(self.max_output_length * self.HEAD_KEEP_RATIO)
        tail_len = self.max_output_length - head_len
        omitted = total - self.max_output_length

        # 落盘只是锦上添花：任何异常都不能让工具本身失败，退化为普通截断即可
        try:
            artifact_path = self._write_output_artifact(result, command=command)
        except Exception as exc:
            logger.warning(f"Failed to persist truncated exec output: {exc}")
            artifact_path = None

        body = (
            result[:head_len]
            + f"\n... (中间省略 {omitted} 个字符，以下为输出末尾) ...\n"
            + result[-tail_len:]
        )
        if artifact_path:
            return (
                body
                + f"\n\n完整输出已保存到: {artifact_path}\n"
                + "需要中间部分时用 read_file 读取该文件（可用 start_line/end_line 定位）。"
            )
        return body

    def _write_output_artifact(self, content: str, *, command: str = "") -> Optional[str]:
        """把完整输出写入 temp 目录，返回相对工作区的路径。

        写盘失败不影响主流程——此时退化为普通截断。

        Args:
            content: 完整输出
            command: 对应命令

        Returns:
            相对工作区的文件路径；写入失败返回 None
        """
        try:
            temp_dir = self.workspace / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            suffix = uuid.uuid4().hex[:6]
            target = temp_dir / f"exec-output-{stamp}-{suffix}.log"

            header = (
                f"# command: {command}\n"
                f"# captured_at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"# total_chars: {len(content)}\n\n"
            )
            target.write_text(header + content, encoding="utf-8")

            try:
                return str(target.relative_to(self.workspace))
            except ValueError:
                return str(target)
        except Exception as exc:
            logger.warning(f"Failed to persist truncated exec output: {exc}")
            return None

    def _terminate_process(self, process) -> None:
        """终止子进程及其进程组。

        只发 SIGTERM 不够：shell 派生的子进程（npm、pytest 等）不会随父进程退出，
        会继续占用端口和 CPU。因此先按进程组终止，超时再强杀。
        """
        if process is None or process.returncode is not None:
            return
        if os.name != "posix":
            # Windows 没有进程组语义：start_new_session 是 POSIX 专有参数，
            # terminate()/kill() 只能结束 cmd.exe 本身。sleep、npm 这类子进程会
            # 存活下来并继续持有继承的 stdout/stderr 管道，等待输出的一方永远
            # 读不到 EOF，表现为取消后调用一直挂到超时。
            self._kill_process_tree_windows(process)
            return

        try:
            # start_new_session=True 使子进程自成进程组，pgid 等于其 pid
            pgid = os.getpgid(process.pid)
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return
        except Exception as exc:
            logger.debug(f"Terminate process failed: {exc}")
            return

        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        except Exception as exc:
            logger.debug(f"Force kill process failed: {exc}")

    @staticmethod
    def _kill_process_tree_windows(process) -> None:
        """用 taskkill /T 递归终止 cmd.exe 下的整棵进程树。

        Windows 上找不到「进程组」，只能按 pid 让系统自己遍历子进程；
        失败（taskkill 不可用等）再退回单进程 kill。
        """
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except Exception as exc:
            logger.debug(f"taskkill process tree failed: {exc}")

        try:
            process.kill()
        except (ProcessLookupError, PermissionError):
            pass
        except Exception as exc:
            logger.debug(f"Force kill process failed: {exc}")

    def _register_cancel_hook(self, process) -> Optional[Callable[[], None]]:
        """把当前进程登记到取消令牌，返回注销函数。

        取消令牌的回调列表没有移除接口，因此用一次性哨兵：取消发生时若无活跃
        进程则什么也不做，避免长会话中回调累积导致误杀后续命令。
        """
        token = self._cancel_token_ctx.get()
        if token is None:
            return None

        active = {"process": process}

        def _on_cancel() -> None:
            self._terminate_process(active.get("process"))

        try:
            token.register_callback(_on_cancel)
        except Exception as exc:
            logger.debug(f"Register cancel hook failed: {exc}")
            return None

        def _unregister() -> None:
            active["process"] = None

        return _unregister

    def _decode_output(self, output: bytes) -> str:
        """解码命令输出，自动检测字符编码
        
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

    def _guard_command(self, command: str, cwd: str) -> Optional[str]:
        """命令安全检查（规则与判定逻辑统一见 command_guard 模块）。"""
        return guard_command(
            command,
            cwd,
            workspace=self.workspace,
            deny_patterns=self.deny_patterns,
            allow_patterns=self.allow_patterns,
            allow_dangerous=self.allow_dangerous,
            restrict_to_workspace=self.restrict_to_workspace,
        )


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
