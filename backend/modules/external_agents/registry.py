"""Registry and config loader for external coding agent profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

from loguru import logger

from backend.modules.external_agents.adapters.cli import CliExternalAgentAdapter
from backend.modules.external_agents.base import (
    ExternalAgentAdapter,
    ExternalAgentProfile,
    ExternalAgentRequest,
    ExternalAgentResult,
)


class ExternalAgentRegistry:
    """Loads configured profiles and dispatches requests to adapters."""

    CONFIG_FILENAME = "external_coding_tools.json"

    def __init__(
        self,
        workspace: Path,
        default_timeout: int = 180,
        max_output_length: int = 10000,
    ) -> None:
        self.workspace = workspace.resolve()
        self.default_timeout = default_timeout
        self.max_output_length = max_output_length
        self.config_path = self.workspace / self.CONFIG_FILENAME
        self._adapters: Dict[str, ExternalAgentAdapter] = {
            "cli": CliExternalAgentAdapter(),
        }
        self._ensure_default_config()

    def list_profiles(self, enabled_only: bool = False) -> List[ExternalAgentProfile]:
        profiles = list(self._load_profiles().values())
        if enabled_only:
            profiles = [profile for profile in profiles if profile.enabled]
        return profiles

    def describe_profiles(self) -> Tuple[List[str], List[str]]:
        """Return enabled profile summaries and disabled profile names."""
        enabled = []
        disabled = []

        for profile in self.list_profiles(enabled_only=False):
            if profile.enabled:
                summary = profile.name
                if profile.description:
                    summary += f" ({profile.description})"
                enabled.append(summary)
            else:
                disabled.append(profile.name)

        return enabled, disabled

    def enabled_profile_names(self) -> List[str]:
        """Return enabled profile names."""
        return [profile.name for profile in self.list_profiles(enabled_only=True)]

    def profile_exists(self, profile_name: str) -> bool:
        """Check whether a profile or alias exists."""
        normalized = profile_name.strip().lower()
        if not normalized:
            return False

        for profile in self._load_profiles().values():
            if profile.name.lower() == normalized:
                return True
            if normalized in [alias.lower() for alias in profile.aliases]:
                return True
        return False

    def resolve_profile_name(self, profile_name: str) -> str:
        """Resolve a profile name or alias to the canonical profile name."""
        normalized = profile_name.strip().lower()
        if not normalized:
            raise ValueError("External coding profile name cannot be empty")

        for profile in self._load_profiles().values():
            if profile.name.lower() == normalized:
                return profile.name
            if normalized in [alias.lower() for alias in profile.aliases]:
                return profile.name

        available = ", ".join(sorted(self._load_profiles())) or "none"
        raise ValueError(
            f"Unknown external coding profile '{profile_name}'. Available profiles: {available}"
        )

    def resolve_profile(self, profile_name: str | None = None) -> ExternalAgentProfile:
        profiles = self._load_profiles()
        enabled_profiles = [profile for profile in profiles.values() if profile.enabled]

        if profile_name:
            canonical_name = self.resolve_profile_name(profile_name)
            profile = profiles.get(canonical_name)
            if profile is None:
                available = ", ".join(sorted(profiles)) or "none"
                raise ValueError(
                    f"Unknown external coding profile '{profile_name}'. Available profiles: {available}"
                )
            if not profile.enabled:
                raise ValueError(
                    f"External coding profile '{profile_name}' is disabled. "
                    f"Enable it in {self.config_path} before use."
                )
            return profile

        if not enabled_profiles:
            raise ValueError(
                "No external coding profiles are enabled. "
                f"Configure and enable one in {self.config_path}."
            )

        if len(enabled_profiles) > 1:
            names = ", ".join(profile.name for profile in enabled_profiles)
            raise ValueError(
                "Multiple external coding profiles are enabled. "
                f"Specify the 'profile' parameter explicitly. Enabled profiles: {names}"
            )

        return enabled_profiles[0]

    async def execute(
        self,
        request: ExternalAgentRequest,
        profile_name: str | None = None,
    ) -> ExternalAgentResult:
        profile = self.resolve_profile(profile_name)
        adapter = self._adapters.get(profile.type)
        if adapter is None:
            raise ValueError(
                f"Profile '{profile.name}' uses unsupported adapter type '{profile.type}'"
            )

        return await adapter.run(
            profile=profile,
            request=request,
            max_output_length=self.max_output_length,
            default_timeout=self.default_timeout,
        )

    def _load_profiles(self) -> Dict[str, ExternalAgentProfile]:
        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            logger.warning(
                "External coding tool config missing, recreating default file: {}",
                self.config_path,
            )
            self._ensure_default_config()
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON in external coding profile config {self.config_path}: {exc}"
            ) from exc

        profiles_raw = raw.get("profiles", [])
        if not isinstance(profiles_raw, list):
            raise ValueError(
                f"Invalid profile config in {self.config_path}: 'profiles' must be a list"
            )

        parsed_profiles: List[ExternalAgentProfile] = []
        for index, item in enumerate(profiles_raw):
            if not isinstance(item, dict):
                raise ValueError(
                    f"Invalid profile config at index {index} in {self.config_path}: expected object"
                )

            profile = self._parse_profile(item, index)
            parsed_profiles.append(profile)

        self._validate_profile_collisions(parsed_profiles)

        profiles: Dict[str, ExternalAgentProfile] = {}
        for profile in parsed_profiles:
            profiles[profile.name] = profile

        return profiles

    def _validate_profile_collisions(
        self,
        profiles: List[ExternalAgentProfile],
    ) -> None:
        """校验 profile 名称和 alias 冲突。"""
        seen_names: Dict[str, str] = {}
        seen_aliases: Dict[str, str] = {}

        for profile in profiles:
            normalized_name = profile.name.strip().lower()
            previous_name_owner = seen_names.get(normalized_name)
            if previous_name_owner is not None:
                raise ValueError(
                    f"Duplicate external coding profile name '{profile.name}' "
                    f"in {self.config_path} (already used by '{previous_name_owner}')"
                )
            if normalized_name in seen_aliases:
                raise ValueError(
                    f"External coding profile name '{profile.name}' conflicts with alias "
                    f"already used by '{seen_aliases[normalized_name]}' in {self.config_path}"
                )
            seen_names[normalized_name] = profile.name

            own_aliases: set[str] = set()
            for alias in profile.aliases:
                normalized_alias = alias.strip().lower()
                if not normalized_alias:
                    continue
                if normalized_alias == normalized_name:
                    raise ValueError(
                        f"External coding profile '{profile.name}' alias '{alias}' "
                        "cannot be the same as its profile name"
                    )
                if normalized_alias in own_aliases:
                    raise ValueError(
                        f"External coding profile '{profile.name}' contains duplicate alias '{alias}'"
                    )
                if normalized_alias in seen_names:
                    raise ValueError(
                        f"External coding profile alias '{alias}' conflicts with profile "
                        f"name '{seen_names[normalized_alias]}' in {self.config_path}"
                    )
                if normalized_alias in seen_aliases:
                    raise ValueError(
                        f"Duplicate external coding profile alias '{alias}' "
                        f"in {self.config_path} (already used by '{seen_aliases[normalized_alias]}')"
                    )
                own_aliases.add(normalized_alias)
                seen_aliases[normalized_alias] = profile.name

    def _parse_profile(
        self,
        item: Dict[str, object],
        index: int,
    ) -> ExternalAgentProfile:
        name = str(item.get("name", "")).strip()
        if not name:
            raise ValueError(
                f"Invalid profile config at index {index} in {self.config_path}: missing name"
            )

        enabled = item.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ValueError(
                f"Invalid profile '{name}' in {self.config_path}: 'enabled' must be a boolean"
            )

        args = item.get("args", [])
        if args is None:
            args = []
        if not isinstance(args, list) or not all(isinstance(value, str) for value in args):
            raise ValueError(
                f"Invalid profile '{name}' in {self.config_path}: 'args' must be a list of strings"
            )

        aliases = item.get("aliases", [])
        if aliases is None:
            aliases = []
        if not isinstance(aliases, list) or not all(
            isinstance(value, str) for value in aliases
        ):
            raise ValueError(
                f"Invalid profile '{name}' in {self.config_path}: 'aliases' must be a list of strings"
            )

        env = item.get("env", {})
        if env is None:
            env = {}
        if not isinstance(env, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in env.items()
        ):
            raise ValueError(
                f"Invalid profile '{name}' in {self.config_path}: 'env' must be an object of strings"
            )

        inherit_env = item.get("inherit_env", [])
        if inherit_env is None:
            inherit_env = []
        if not isinstance(inherit_env, list) or not all(
            isinstance(value, str) for value in inherit_env
        ):
            raise ValueError(
                f"Invalid profile '{name}' in {self.config_path}: 'inherit_env' must be a list of strings"
            )

        session_mode = str(item.get("session_mode", "history") or "history").strip()
        if session_mode not in {"stateless", "history", "native"}:
            raise ValueError(
                f"Invalid profile '{name}' in {self.config_path}: 'session_mode' "
                "must be one of stateless, history, native"
            )

        history_message_count = item.get("history_message_count", 10)
        if not isinstance(history_message_count, int):
            raise ValueError(
                f"Invalid profile '{name}' in {self.config_path}: 'history_message_count' must be an integer"
            )
        if history_message_count < 1 or history_message_count > 50:
            raise ValueError(
                f"Invalid profile '{name}' in {self.config_path}: 'history_message_count' must be between 1 and 50"
            )

        success_exit_codes = item.get("success_exit_codes", [0])
        if not isinstance(success_exit_codes, list) or not all(
            isinstance(code, int) for code in success_exit_codes
        ):
            raise ValueError(
                f"Invalid profile '{name}' in {self.config_path}: 'success_exit_codes' must be a list of integers"
            )

        timeout = item.get("timeout")
        if timeout is not None and not isinstance(timeout, int):
            raise ValueError(
                f"Invalid profile '{name}' in {self.config_path}: 'timeout' must be an integer"
            )
        if isinstance(timeout, int) and timeout <= 0:
            raise ValueError(
                f"Invalid profile '{name}' in {self.config_path}: 'timeout' must be greater than 0"
            )

        working_dir = item.get("working_dir", "")
        if working_dir is None:
            working_dir = ""
        if not isinstance(working_dir, str):
            raise ValueError(
                f"Invalid profile '{name}' in {self.config_path}: 'working_dir' must be a string"
            )

        icon_svg = item.get("icon_svg", "")
        if icon_svg is None:
            icon_svg = ""
        if not isinstance(icon_svg, str):
            raise ValueError(
                f"Invalid profile '{name}' in {self.config_path}: 'icon_svg' must be a string"
            )

        return ExternalAgentProfile(
            name=name,
            aliases=[str(value).strip() for value in aliases if str(value).strip()],
            type=str(item.get("type", "cli")).strip() or "cli",
            icon_svg=str(icon_svg).strip(),
            description=str(item.get("description", "")).strip(),
            enabled=enabled,
            command=str(item.get("command", "")).strip(),
            args=list(args),
            working_dir=str(working_dir).strip(),
            stdin_template=(
                str(item["stdin_template"])
                if isinstance(item.get("stdin_template"), str)
                else None
            ),
            env=dict(env),
            inherit_env=list(inherit_env),
            session_mode=session_mode,
            history_message_count=history_message_count,
            timeout=timeout,
            success_exit_codes=list(success_exit_codes) or [0],
        )

    def _ensure_default_config(self) -> None:
        if self.config_path.exists():
            return

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(self._default_config(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info("Created default external coding profile config: {}", self.config_path)

    def _default_config(self) -> Dict[str, object]:
        return {
            "version": 1,
            "profiles": [
                {
                    "name": "claude",
                    "aliases": ["claude-code"],
                    "type": "cli",
                    "icon_svg": "",
                    "enabled": False,
                    "description": "",
                    "command": "claude",
                    "args": ["-p", "{prompt}"],
                    "working_dir": "",
                    "inherit_env": ["ANTHROPIC_API_KEY"],
                    "session_mode": "native",
                    "history_message_count": 10,
                    "timeout": 900,
                },
                {
                    "name": "codex",
                    "aliases": ["openai-codex"],
                    "type": "cli",
                    "icon_svg": "",
                    "enabled": False,
                    "description": "",
                    "command": "codex",
                    "args": [
                        "exec",
                        "--skip-git-repo-check",
                        "--cd",
                        "{working_dir}",
                        "-"
                    ],
                    "working_dir": "",
                    "stdin_template": "{prompt}",
                    "inherit_env": ["OPENAI_API_KEY"],
                    "session_mode": "history",
                    "history_message_count": 10,
                    "timeout": 900,
                },
                {
                    "name": "opencode",
                    "aliases": ["open-code"],
                    "type": "cli",
                    "icon_svg": "",
                    "enabled": False,
                    "description": "",
                    "command": "opencode",
                    "args": ["run", "{prompt}"],
                    "working_dir": "",
                    "inherit_env": [
                        "OPENAI_API_KEY",
                        "ANTHROPIC_API_KEY",
                        "OPENCODE_CONFIG",
                        "OPENCODE_CONFIG_CONTENT",
                    ],
                    "session_mode": "history",
                    "history_message_count": 10,
                    "timeout": 900,
                },
            ],
        }
