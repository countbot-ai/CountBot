"""Tool wrapper for invoking configurable external coding agents."""

from __future__ import annotations

import contextvars
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.modules.external_agents.base import ExternalAgentRequest
from backend.modules.external_agents.registry import ExternalAgentRegistry
from backend.modules.tools.base import Tool


class ExternalCodingAgentTool(Tool):
    """Dispatch coding tasks to configured external agent profiles."""

    def __init__(
        self,
        workspace: Path,
        default_timeout: int = 180,
        max_output_length: int = 10000,
    ) -> None:
        self.workspace = workspace.resolve()
        self.default_timeout = default_timeout
        self.max_output_length = max_output_length
        self._session_id_context: contextvars.ContextVar[Optional[str]] = (
            contextvars.ContextVar("external_coding_agent_session_id", default=None)
        )
        self._cancel_token_context: contextvars.ContextVar[Optional[object]] = (
            contextvars.ContextVar("external_coding_agent_cancel_token", default=None)
        )
        self.registry = ExternalAgentRegistry(
            workspace=self.workspace,
            default_timeout=default_timeout,
            max_output_length=max_output_length,
        )

    def set_session_id(self, session_id: Optional[str]) -> None:
        self._session_id_context.set(session_id)

    def set_cancel_token(self, cancel_token: Optional[object]) -> None:
        self._cancel_token_context.set(cancel_token)

    @property
    def name(self) -> str:
        return "external_coding_agent"

    @property
    def description(self) -> str:
        try:
            enabled, disabled = self.registry.describe_profiles()
            enabled_text = ", ".join(enabled) if enabled else "none"
            disabled_text = ", ".join(disabled) if disabled else "none"
        except Exception as exc:
            enabled_text = "unavailable"
            disabled_text = f"config error: {exc}"

        return (
            "Run a configured external coding agent such as Claude Code, Codex, OpenCode, "
            "or another local CLI profile. Use this when a task benefits from handing "
            "off work to an external programming assistant. "
            f"Enabled profiles: {enabled_text}. Disabled profiles: {disabled_text}. "
            f"Profile config file: {self.registry.config_path}."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Required. The coding task to give the external agent.",
                    "minLength": 1,
                },
                "profile": {
                    "type": "string",
                    "description": (
                        "Optional profile name from external_coding_tools.json. "
                        "Required when multiple profiles are enabled."
                    ),
                },
                "mode": {
                    "type": "string",
                    "description": "Optional task mode hint for the external agent.",
                    "enum": ["run", "analyze", "edit", "review", "debug"],
                },
                "working_dir": {
                    "type": "string",
                    "description": (
                        "Optional working directory relative to the current workspace. "
                        "Defaults to workspace root."
                    ),
                },
                "context_files": {
                    "type": "array",
                    "description": (
                        "Optional list of relevant workspace-relative file paths to mention "
                        "in the prompt sent to the external agent."
                    ),
                    "items": {"type": "string"},
                },
                "extra_instructions": {
                    "type": "string",
                    "description": "Optional extra constraints or formatting instructions.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Optional per-call timeout in seconds.",
                    "minimum": 10,
                    "maximum": 3600,
                },
            },
            "required": ["task"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: Any) -> str:
        task = str(kwargs.get("task", "")).strip()
        profile_name = kwargs.get("profile")
        mode = str(kwargs.get("mode", "run") or "run")
        working_dir = str(kwargs.get("working_dir", "") or "").strip()
        context_files = list(kwargs.get("context_files") or [])
        extra_instructions = str(kwargs.get("extra_instructions", "") or "").strip()
        timeout = kwargs.get("timeout")

        if not task:
            return "Error: 'task' is required."

        try:
            cancel_token = self._cancel_token_context.get()
            if cancel_token is not None and getattr(cancel_token, "is_cancelled", False):
                return "Error: external coding task cancelled."

            profile = self.registry.resolve_profile(
                str(profile_name).strip() if profile_name else None
            )
            resolved_working_dir = self._resolve_working_dir(
                working_dir,
                profile.working_dir,
            )
            request = ExternalAgentRequest(
                task=task,
                prompt=self._build_prompt(
                    task=task,
                    mode=mode,
                    working_dir=resolved_working_dir,
                    context_files=context_files,
                    extra_instructions=extra_instructions,
                ),
                workspace=self.workspace,
                working_dir=resolved_working_dir,
                mode=mode,
                context_files=context_files,
                extra_instructions=extra_instructions,
                timeout=timeout,
                session_id=self._session_id_context.get(),
                cancel_token=cancel_token,
            )
            result = await self.registry.execute(
                request=request,
                profile_name=profile.name,
            )
            if cancel_token is not None and getattr(cancel_token, "is_cancelled", False):
                return "Error: external coding task cancelled."
            return result.to_text()
        except Exception as exc:
            return str(exc) if str(exc).startswith("Error:") else f"Error: {exc}"

    def _resolve_working_dir(self, working_dir: str, default_working_dir: str = "") -> Path:
        target_dir = working_dir or default_working_dir
        if not target_dir:
            return self.workspace

        candidate = Path(target_dir).expanduser()
        target = candidate.resolve() if candidate.is_absolute() else (self.workspace / candidate).resolve()
        try:
            target.relative_to(self.workspace)
        except ValueError as exc:
            raise ValueError(
                f"Working directory must stay inside workspace: {target_dir}"
            ) from exc
        if not target.exists():
            raise ValueError(f"Working directory does not exist: {target_dir}")
        if not target.is_dir():
            raise ValueError(f"Working directory is not a directory: {target_dir}")
        return target

    def _build_prompt(
        self,
        task: str,
        mode: str,
        working_dir: Path,
        context_files: List[str],
        extra_instructions: str,
    ) -> str:
        lines = [
            "You are an external coding agent invoked by CountBot.",
            f"Mode: {mode}",
            f"Workspace: {self.workspace}",
            f"Working directory: {working_dir}",
            "",
            "Task:",
            task,
        ]

        if context_files:
            lines.extend(
                [
                    "",
                    "Relevant files:",
                    *[f"- {path}" for path in context_files],
                ]
            )

        if extra_instructions:
            lines.extend(
                [
                    "",
                    "Additional instructions:",
                    extra_instructions,
                ]
            )

        lines.extend(
            [
                "",
                "Return concise, execution-oriented output. "
                "If you modify files, mention the important files changed.",
            ]
        )

        return "\n".join(lines)
