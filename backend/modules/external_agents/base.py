"""Base types for external coding agent integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from backend.modules.agent.task_manager import CancellationToken


@dataclass(slots=True)
class ExternalAgentProfile:
    """Static profile describing how to launch an external coding tool."""

    name: str
    type: str
    aliases: List[str] = field(default_factory=list)
    icon_svg: str = ""
    description: str = ""
    enabled: bool = False
    command: str = ""
    args: List[str] = field(default_factory=list)
    working_dir: str = ""
    stdin_template: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    inherit_env: List[str] = field(default_factory=list)
    session_mode: str = "history"
    history_message_count: int = 10
    timeout: Optional[int] = None
    success_exit_codes: List[int] = field(default_factory=lambda: [0])


@dataclass(slots=True)
class ExternalAgentRequest:
    """Normalized request passed to adapters."""

    task: str
    prompt: str
    workspace: Path
    working_dir: Path
    mode: str = "run"
    context_files: List[str] = field(default_factory=list)
    extra_instructions: str = ""
    timeout: Optional[int] = None
    session_id: Optional[str] = None
    cancel_token: Optional["CancellationToken"] = None


@dataclass(slots=True)
class ExternalAgentResult:
    """Normalized adapter result."""

    profile_name: str
    adapter_type: str
    command: List[str]
    working_dir: Path
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    cancelled: bool = False
    success_exit_codes: List[int] = field(default_factory=lambda: [0])

    @property
    def success(self) -> bool:
        return (
            not self.timed_out
            and not self.cancelled
            and self.exit_code in (self.success_exit_codes or [0])
        )

    def to_text(self) -> str:
        """Render a chat-friendly tool result."""
        stdout = self.stdout.strip()
        stderr = self.stderr.strip()

        if self.cancelled:
            return "任务已取消。"

        if self.timed_out:
            details = stderr or stdout
            if details:
                return f"执行超时。\n\n{details}"
            return "执行超时。"

        if self.success:
            if stdout:
                return stdout
            if stderr:
                return stderr
            return "执行完成，但没有返回内容。"

        lines = [f"执行失败，退出码 {self.exit_code}。"]
        if stderr:
            lines.extend(["", stderr])
        elif stdout:
            lines.extend(["", stdout])
        return "\n".join(lines)


class ExternalAgentAdapter(ABC):
    """Adapter interface for external coding tools."""

    @property
    @abstractmethod
    def adapter_type(self) -> str:
        """Unique adapter type name."""

    @abstractmethod
    async def run(
        self,
        profile: ExternalAgentProfile,
        request: ExternalAgentRequest,
        max_output_length: int,
        default_timeout: int,
    ) -> ExternalAgentResult:
        """Execute the request using the provided profile."""
