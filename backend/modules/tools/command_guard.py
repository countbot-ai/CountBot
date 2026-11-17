"""Shell 命令安全守卫。"""

import re
from pathlib import Path
from typing import List, Optional, Sequence

from loguru import logger


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
    # 管道直接进 shell（curl ... | sh、base64 -d | bash 等），
    # 载荷完全绕过下方的路径/危险模式检查
    r"\|\s*(?:sudo\s+)?(?:ba|z|da|k|fi|s)?sh\b",
    # 管道进脚本解释器并从 stdin 读代码（... | python3 -、| perl - 等），
    # 以及裸管道进解释器（... | python3 无参数时同样从 stdin 读程序）
    r"\|\s*(?:python3?|perl|ruby|php|node|deno|bun|lua|osascript)\s+(?:-[A-Za-z]+\s+)*-\s*$",
    r"\|\s*(?:python3?|perl|ruby|node)\s*$",
]

# 解释器内联代码载荷（python3 -c / perl -e / node -e / sh -c 等）：
# 任意路径与任意代码都可以藏进引号内的字符串里，
# 下方的路径提取正则无法覆盖，restrict 模式下必须整体拒绝。
INLINE_CODE_PATTERN = re.compile(
    r"\b(?:python3?|pypy3?|perl|ruby|php|node|deno|bun|lua|luajit|"
    r"bash|sh|zsh|ksh|dash|fish|osascript|tclsh|wish)\b"
    r"(?:\s+(?:-\w+|--[\w-]+))*"          # 中间允许夹带其它选项
    r"\s+(?:-[A-Za-z]*[cer]\b|--command\b|--eval\b|--execute\b)"
)


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


def guard_command(
    command: str,
    cwd: str,
    *,
    workspace: Path,
    deny_patterns: Sequence[str],
    allow_patterns: Optional[Sequence[str]],
    allow_dangerous: bool,
    restrict_to_workspace: bool,
) -> Optional[str]:
    """命令安全检查

    Args:
        command: 待检查的命令
        cwd: 工作目录路径
        workspace: 工作空间根目录
        deny_patterns: 拒绝模式列表
        allow_patterns: 允许模式白名单，None 表示不启用
        allow_dangerous: 是否允许危险命令
        restrict_to_workspace: 是否限制在工作空间内

    Returns:
        str | None: 如果命令被阻止返回错误信息，否则返回 None
    """
    cmd = command.strip()
    lower = cmd.lower()

    def matches_pattern(pattern: str) -> tuple[bool, Optional[str]]:
        try:
            return bool(re.search(pattern, lower)), None
        except re.error as exc:
            logger.warning(f"Invalid safety regex pattern ignored during exec guard: {pattern} ({exc})")
            return False, f"{pattern}: {exc}"

    # 白名单检查
    if allow_patterns is not None:
        if not allow_patterns:
            return "Error: Command blocked by safety guard (allowlist is empty)"
        allowlist_errors: List[str] = []
        for pattern in allow_patterns:
            matched, error = matches_pattern(pattern)
            if error:
                allowlist_errors.append(error)
                continue
            if matched:
                break
        else:
            if allowlist_errors:
                return (
                    "Error: Command blocked by safety guard "
                    f"(invalid allowlist regex: {allowlist_errors[0]})"
                )
            return "Error: Command blocked by safety guard (not in allowlist)"

    # 危险模式检查
    if not allow_dangerous:
        for pattern in deny_patterns:
            matched, error = matches_pattern(pattern)
            if error:
                return (
                    "Error: Command blocked by safety guard "
                    f"(invalid denylist regex: {error})"
                )
            if matched:
                return (
                    "Error: Command blocked by safety guard "
                    "(dangerous pattern detected). "
                    "Next: rewrite the command without destructive operations "
                    "(e.g. rm -rf) and retry."
                )

    # 工作空间路径限制
    if restrict_to_workspace:
        # 路径遍历检查
        if "..\\" in cmd or "../" in cmd:
            return "Error: Command blocked by safety guard (path traversal detected)"

        # 解释器内联代码检查：python3 -c "open('/etc/passwd')" 这类载荷
        # 把任意路径藏进引号内的代码字符串，下方的路径提取正则覆盖不到，
        # 且解释器可在代码内逃逸出所有基于命令文本的检查。
        if INLINE_CODE_PATTERN.search(lower):
            return (
                "Error: Command blocked by safety guard "
                "(interpreter inline code is not allowed while workspace "
                "restriction is enabled). "
                "Next: write the code to a script file inside the working "
                "directory and run it as a plain command (e.g. "
                "`python3 script.py`), then retry."
            )

        # 命令替换检查：$(...) 和反引号的输出不经过本守卫，
        # 可用于拼接出工作区外的路径或任意命令。
        if "$(" in cmd or "`" in cmd:
            return (
                "Error: Command blocked by safety guard "
                "(command substitution is not allowed while workspace "
                "restriction is enabled). "
                "Next: use literal paths inside the working directory and retry."
            )

        # heredoc / here-string 检查：载荷不在命令文本里，守卫不可见。
        if re.search(r"<<-?", lower):
            return (
                "Error: Command blocked by safety guard "
                "(heredoc is not allowed while workspace restriction is "
                "enabled). "
                "Next: write the content to a file inside the working "
                "directory with the write tool, then retry."
            )

        cwd_path = Path(cwd).resolve()

        # 提取命令中的路径（排除 URL）
        # 先移除 URL 避免误判
        cmd_without_urls = re.sub(r'https?://[^\s"\']+', '', cmd)

        # Windows 绝对路径：C:\path\to\file
        win_paths = re.findall(r"[A-Za-z]:\\[^\s\"']+", cmd_without_urls)

        # POSIX 绝对路径：以 / 开头，前缀可以是空格/行首（裸路径），
        # 也可以是引号或括号（引号内的路径，如 open('/etc/passwd')），
        # 但排除相对路径中的斜杠
        posix_paths = re.findall(
            r"""(?:^|[\s"'=(])(/[^\s"'(){}]+)""", cmd_without_urls
        )

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
                    p.relative_to(workspace)
                except ValueError:
                    return (
                        f"Error: Command blocked by safety guard "
                        f"(path outside working dir: {raw}). "
                        f"Next: rewrite the command to use a path inside the "
                        f"working directory and retry."
                    )

    return None
