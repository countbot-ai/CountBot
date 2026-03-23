"""CLI-backed adapter for external coding agents."""

from __future__ import annotations

import asyncio
import locale
import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Dict, List

from loguru import logger

from backend.modules.external_agents.base import (
    ExternalAgentAdapter,
    ExternalAgentProfile,
    ExternalAgentRequest,
    ExternalAgentResult,
)
from backend.modules.external_agents.conversation import resolve_effective_session_mode


class CliExternalAgentAdapter(ExternalAgentAdapter):
    """Run an external coding agent via a local CLI process."""

    _BASE_ENV_NAMES = [
        "PATH",
        "HOME",
        "USER",
        "USERNAME",
        "LOGNAME",
        "SHELL",
        "TMPDIR",
        "TMP",
        "TEMP",
        "LANG",
        "LC_ALL",
        "TERM",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "SYSTEMROOT",
        "COMSPEC",
        "PATHEXT",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
    ]

    @property
    def adapter_type(self) -> str:
        return "cli"

    async def run(
        self,
        profile: ExternalAgentProfile,
        request: ExternalAgentRequest,
        max_output_length: int,
        default_timeout: int,
    ) -> ExternalAgentResult:
        command = self._resolve_command(profile.command)
        if not command:
            raise ValueError(
                f"Profile '{profile.name}' command is not executable: {profile.command}"
            )

        variables = self._build_template_variables(request)
        argv = self._build_argv(command, profile, request, variables)
        env = self._build_env(profile, variables)
        timeout = self._resolve_timeout(profile, request, default_timeout)

        logger.info(
            "Launching external coding agent '{}' via CLI: {}",
            profile.name,
            " ".join(argv),
        )

        stdin_bytes = None
        if profile.stdin_template is not None:
            stdin_bytes = profile.stdin_template.format_map(variables).encode("utf-8")

        subprocess_kwargs = {}
        if os.name == "nt":
            subprocess_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            subprocess_kwargs["start_new_session"] = True

        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(request.working_dir),
            env=env,
            stdin=asyncio.subprocess.PIPE if stdin_bytes is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **subprocess_kwargs,
        )

        timed_out = False
        cancelled = bool(request.cancel_token and request.cancel_token.is_cancelled)

        def _cancel_process() -> None:
            self._terminate_process(process, profile.name, "cancelled")

        if request.cancel_token is not None:
            request.cancel_token.register_callback(_cancel_process)

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(stdin_bytes),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            timed_out = True
            self._terminate_process(process, profile.name, "timed out")
            stdout, stderr = await process.communicate()
        except asyncio.CancelledError:
            self._terminate_process(process, profile.name, "task cancelled")
            try:
                await process.communicate()
            except Exception:
                pass
            raise

        cancelled = bool(request.cancel_token and request.cancel_token.is_cancelled)

        stdout_text = self._truncate(self._decode_output(stdout), max_output_length)
        stderr_text = self._truncate(self._decode_output(stderr), max_output_length)
        exit_code = process.returncode if process.returncode is not None else -1
        if timed_out:
            exit_code = exit_code if exit_code is not None and exit_code >= 0 else -1
            logger.warning(
                "External coding agent '{}' timed out after {}s",
                profile.name,
                timeout,
            )
        elif cancelled:
            logger.info(
                "External coding agent '{}' cancelled before completion",
                profile.name,
            )

        if (
            not timed_out
            and not cancelled
            and profile.success_exit_codes
            and exit_code not in profile.success_exit_codes
        ):
            logger.warning(
                "External coding agent '{}' returned non-success exit code {}",
                profile.name,
                exit_code,
            )

        return ExternalAgentResult(
            profile_name=profile.name,
            adapter_type=self.adapter_type,
            command=argv,
            working_dir=request.working_dir,
            exit_code=exit_code,
            stdout=stdout_text,
            stderr=stderr_text,
            timed_out=timed_out,
            cancelled=cancelled,
            success_exit_codes=list(profile.success_exit_codes) or [0],
        )

    def _resolve_command(self, command: str) -> str:
        if not command:
            return ""

        command_path = Path(command).expanduser()
        if command_path.is_absolute():
            return str(command_path) if self._is_executable_file(command_path) else ""
        if command_path.parent != Path("."):
            candidate = command_path.resolve()
            return str(candidate) if self._is_executable_file(candidate) else ""

        resolved = shutil.which(command)
        return resolved or ""

    def _is_executable_file(self, path: Path) -> bool:
        return path.is_file() and os.access(path, os.X_OK)

    def _resolve_timeout(
        self,
        profile: ExternalAgentProfile,
        request: ExternalAgentRequest,
        default_timeout: int,
    ) -> int:
        if profile.timeout is not None:
            return profile.timeout
        if request.timeout is not None:
            return request.timeout
        return default_timeout

    def _build_argv(
        self,
        command: str,
        profile: ExternalAgentProfile,
        request: ExternalAgentRequest,
        variables: Dict[str, str],
    ) -> List[str]:
        formatted_args = [arg.format_map(variables) for arg in profile.args]
        session_mode = resolve_effective_session_mode(profile)

        if session_mode == "native" and request.session_id:
            command_name = Path(command).name.lower()
            if command_name == "claude" or profile.name.strip().lower() == "claude":
                if "--session-id" in formatted_args:
                    return [command, *formatted_args]
                return [command, "--session-id", request.session_id, *formatted_args]

        return [command, *formatted_args]

    def _build_template_variables(self, request: ExternalAgentRequest) -> Dict[str, str]:
        return {
            "task": request.task,
            "prompt": request.prompt,
            "mode": request.mode,
            "workspace": str(request.workspace),
            "working_dir": str(request.working_dir),
            "context_files": "\n".join(request.context_files),
            "context_files_csv": ", ".join(request.context_files),
            "session_id": request.session_id or "",
            "extra_instructions": request.extra_instructions,
        }

    def _build_env(
        self,
        profile: ExternalAgentProfile,
        variables: Dict[str, str],
    ) -> Dict[str, str]:
        env: Dict[str, str] = {}
        copied_names: set[str] = set()

        for name in [*self._BASE_ENV_NAMES, *profile.inherit_env]:
            normalized = str(name or "").strip()
            if not normalized or normalized in copied_names:
                continue
            copied_names.add(normalized)
            value = os.environ.get(normalized)
            if value is not None:
                env[normalized] = value

        if "PATH" not in env:
            env["PATH"] = os.defpath

        for key, value in profile.env.items():
            env[key] = value.format_map(variables)

        return env

    def _terminate_process(
        self,
        process: asyncio.subprocess.Process,
        profile_name: str,
        reason: str,
    ) -> None:
        if process.returncode is not None:
            return

        try:
            if os.name != "nt" and process.pid:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            return
        except Exception as exc:
            logger.warning(
                "Failed to terminate external coding agent '{}' on {}: {}",
                profile_name,
                reason,
                exc,
            )

    def _decode_output(self, output: bytes) -> str:
        if not output:
            return ""

        system_encoding = locale.getpreferredencoding() or "utf-8"
        encodings_to_try: List[str] = [
            system_encoding,
            "utf-8",
            "gbk",
            "gb2312",
            "cp936",
        ]

        seen = set()
        for encoding in encodings_to_try:
            if encoding in seen:
                continue
            seen.add(encoding)
            try:
                return output.decode(encoding)
            except UnicodeDecodeError:
                continue

        return output.decode("utf-8", errors="replace")

    def _truncate(self, text: str, max_output_length: int) -> str:
        if len(text) <= max_output_length:
            return text

        hidden = len(text) - max_output_length
        return text[:max_output_length] + f"\n... (truncated {hidden} chars)"
