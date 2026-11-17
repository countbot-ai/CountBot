"""多用户功能的运行时开关：部署级环境变量优先于 settings 表中的运营级开关。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from loguru import logger

# ---------------------------------------------------------------------------
# settings 表中的键名
# ---------------------------------------------------------------------------

KEY_ENABLED = "multiuser.enabled"
KEY_REGISTRATION_OPEN = "multiuser.registration.open"
KEY_REGISTRATION_APPROVAL = "multiuser.registration.approval"
KEY_MODE = "multiuser.mode"
KEY_SHARED_PROVIDERS = "multiuser.shared.providers"
KEY_SHARED_SKILLS_WIKI_MCP = "multiuser.shared.skills_wiki_mcp"
KEY_USER_MCP_ENABLED = "multiuser.user_mcp.enabled"
KEY_USER_MCP_STDIO_ALLOWLIST = "multiuser.user_mcp.stdio_allowlist"
KEY_NOTIFY_SHARED_CHANNELS = "multiuser.notify.shared_channels"

APPROVAL_MANUAL = "manual"
APPROVAL_AUTO = "auto"

MODE_SHARED = "shared"
MODE_ISOLATED = "isolated"


@dataclass(frozen=True)
class MultiuserSettings:
    """一次读取所得到的多用户设置快照。"""

    enabled: bool = False
    registration_open: bool = False
    approval: str = APPROVAL_MANUAL
    mode: str = MODE_SHARED
    shared_providers: bool = True
    shared_skills_wiki_mcp: bool = False
    # 用户自建 MCP：总开关 + stdio 命令白名单（空表示不开放 stdio）
    allow_user_mcp: bool = True
    user_mcp_stdio_allowlist: tuple[str, ...] = ()
    # 允许普通用户复用的通知渠道（空表示一个都不共享，用户只能自建推送）
    notify_shared_channels: tuple[str, ...] = ()
    # 部署级硬开关的最终生效值
    allow_local_admin_bypass: bool = True
    max_users: int = 0

    @property
    def registration_allowed(self) -> bool:
        return self.enabled and self.registration_open

    @property
    def approval_auto(self) -> bool:
        return self.approval == APPROVAL_AUTO


# 进程内缓存；管理员改设置后由 invalidate_cache() 清理
_cache: Optional[MultiuserSettings] = None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        logger.warning(f"Invalid int for {name}: {raw!r}, falling back to {default}")
        return default


def _coerce_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _coerce_str_list(value, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    """把 DB/环境变量里的字符串列表收敛为去重元组。"""
    if value is None:
        return default
    if isinstance(value, str):
        items = [part.strip() for part in value.replace("\n", ",").split(",")]
    elif isinstance(value, (list, tuple, set)):
        items = [str(part).strip() for part in value]
    else:
        return default
    return tuple(dict.fromkeys(item for item in items if item))


def invalidate_cache() -> None:
    """管理员修改设置后调用，使下次读取重新落库。"""
    global _cache
    _cache = None


def peek_settings() -> MultiuserSettings:
    """同步读取已缓存的设置快照，未加载时返回默认值。"""
    return _cache if _cache is not None else MultiuserSettings()


async def _read_raw_settings() -> dict:
    from sqlalchemy import select

    from backend.database import AsyncSessionLocal
    from backend.models.setting import Setting

    keys = (
        KEY_ENABLED,
        KEY_REGISTRATION_OPEN,
        KEY_REGISTRATION_APPROVAL,
        KEY_MODE,
        KEY_SHARED_PROVIDERS,
        KEY_SHARED_SKILLS_WIKI_MCP,
        KEY_USER_MCP_ENABLED,
        KEY_USER_MCP_STDIO_ALLOWLIST,
        KEY_NOTIFY_SHARED_CHANNELS,
    )
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Setting).where(Setting.key.in_(keys)))
            raw: dict = {}
            for setting in result.scalars().all():
                try:
                    raw[setting.key] = json.loads(setting.value)
                except (json.JSONDecodeError, TypeError):
                    raw[setting.key] = setting.value
            return raw
    except Exception as exc:  # 读失败不能影响主流程，按默认值处理
        logger.warning(f"Failed to read multiuser settings: {exc}")
        return {}


async def load_settings(use_cache: bool = True) -> MultiuserSettings:
    """读取多用户设置快照；环境变量硬开关具备最终否决权。"""
    global _cache
    if use_cache and _cache is not None:
        return _cache

    raw = await _read_raw_settings()

    enabled = _coerce_bool(raw.get(KEY_ENABLED), False)
    # 部署级总开关：一旦显式设为 false，忽略 DB
    if os.getenv("COUNTBOT_MULTIUSER_ENABLED") is not None:
        enabled = _env_bool("COUNTBOT_MULTIUSER_ENABLED", enabled)

    approval = str(raw.get(KEY_REGISTRATION_APPROVAL) or APPROVAL_MANUAL).strip().lower()
    if approval not in (APPROVAL_MANUAL, APPROVAL_AUTO):
        approval = APPROVAL_MANUAL

    mode = str(raw.get(KEY_MODE) or MODE_SHARED).strip().lower()
    if mode not in (MODE_SHARED, MODE_ISOLATED):
        mode = MODE_SHARED

    stdio_allowlist = _coerce_str_list(raw.get(KEY_USER_MCP_STDIO_ALLOWLIST))
    # 部署级环境变量优先级更高，便于运维在受限环境统一收紧
    if os.getenv("COUNTBOT_USER_MCP_STDIO_ALLOWLIST") is not None:
        stdio_allowlist = _coerce_str_list(os.getenv("COUNTBOT_USER_MCP_STDIO_ALLOWLIST"))

    settings = MultiuserSettings(
        enabled=enabled,
        registration_open=_coerce_bool(raw.get(KEY_REGISTRATION_OPEN), False),
        approval=approval,
        mode=mode,
        shared_providers=_coerce_bool(raw.get(KEY_SHARED_PROVIDERS), True),
        shared_skills_wiki_mcp=_coerce_bool(raw.get(KEY_SHARED_SKILLS_WIKI_MCP), False),
        allow_user_mcp=_coerce_bool(raw.get(KEY_USER_MCP_ENABLED), True),
        user_mcp_stdio_allowlist=stdio_allowlist,
        notify_shared_channels=_coerce_str_list(raw.get(KEY_NOTIFY_SHARED_CHANNELS)),
        allow_local_admin_bypass=_env_bool("COUNTBOT_ALLOW_LOCAL_ADMIN_BYPASS", True),
        max_users=_env_int("COUNTBOT_MAX_USERS", 0),
    )

    _cache = settings
    return settings


async def save_settings(**changes) -> MultiuserSettings:
    """写入多用户设置并清缓存；只接受已知键，非法值保持原值。"""
    from backend.database import AsyncSessionLocal
    from backend.models.setting import Setting

    updates: dict[str, object] = {}

    if "enabled" in changes and changes["enabled"] is not None:
        updates[KEY_ENABLED] = bool(changes["enabled"])
    for field, key in (
        ("registration_open", KEY_REGISTRATION_OPEN),
        ("shared_providers", KEY_SHARED_PROVIDERS),
        ("shared_skills_wiki_mcp", KEY_SHARED_SKILLS_WIKI_MCP),
        ("allow_user_mcp", KEY_USER_MCP_ENABLED),
    ):
        if field in changes and changes[field] is not None:
            updates[key] = bool(changes[field])
    if "user_mcp_stdio_allowlist" in changes and changes["user_mcp_stdio_allowlist"] is not None:
        updates[KEY_USER_MCP_STDIO_ALLOWLIST] = list(
            _coerce_str_list(changes["user_mcp_stdio_allowlist"])
        )
    if (
        "notify_shared_channels" in changes
        and changes["notify_shared_channels"] is not None
    ):
        updates[KEY_NOTIFY_SHARED_CHANNELS] = list(
            _coerce_str_list(changes["notify_shared_channels"])
        )
    if "approval" in changes and changes["approval"] is not None:
        value = str(changes["approval"]).strip().lower()
        if value in (APPROVAL_MANUAL, APPROVAL_AUTO):
            updates[KEY_REGISTRATION_APPROVAL] = value
    if "mode" in changes and changes["mode"] is not None:
        value = str(changes["mode"]).strip().lower()
        if value in (MODE_SHARED, MODE_ISOLATED):
            updates[KEY_MODE] = value

    if updates:
        async with AsyncSessionLocal() as session:
            for key, value in updates.items():
                await session.merge(Setting(key=key, value=json.dumps(value)))
            await session.commit()

    invalidate_cache()
    return await load_settings(use_cache=False)


async def is_enabled() -> bool:
    return (await load_settings()).enabled


async def local_admin_bypass_allowed() -> bool:
    """本机直连是否可免登录当管理员。

    多用户模式下恒定关闭：否则本机任意进程、或任何能打 127.0.0.1 的 SSRF，
    都能直接拿到管理员权限。桌面单用户模式保持原有旁路行为。
    """
    settings = await load_settings()
    return bool(settings.allow_local_admin_bypass) and not settings.enabled
