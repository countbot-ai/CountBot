"""渠道管理 API 端点"""

import asyncio
import re
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Any, Dict, Optional
from loguru import logger

from backend.modules.config.loader import config_loader
from backend.modules.channels.manager import ChannelManager
from backend.modules.channels.onboarding import (
    begin_onboarding,
    drop_onboarding_session,
    poll_onboarding,
    supports_onboarding,
)
from backend.modules.external_agents.registry import ExternalAgentRegistry
from backend.modules.multiuser.permissions import require_active_user, require_admin

router = APIRouter(
    prefix="/api/channels",
    tags=["channels"],
    dependencies=[Depends(require_active_user)],
)

# 全局渠道管理器实例（将在应用启动时初始化）
_channel_manager: Optional[ChannelManager] = None


def set_channel_manager(manager: ChannelManager):
    """设置全局渠道管理器实例"""
    global _channel_manager
    _channel_manager = manager


def get_channel_manager() -> ChannelManager:
    """获取渠道管理器实例"""
    if _channel_manager is None:
        raise HTTPException(status_code=500, detail="Channel manager not initialized")
    return _channel_manager


class ChannelConfigUpdate(BaseModel):
    """渠道配置更新请求"""
    channel: str
    config: Dict[str, Any]


class ChannelTestRequest(BaseModel):
    """渠道测试请求"""
    channel: str
    config: Optional[Dict[str, Any]] = None  # 可选的临时配置
    account_id: Optional[str] = None


class WeChatLoginStartRequest(BaseModel):
    """微信扫码登录启动请求。"""

    config: Optional[Dict[str, Any]] = None
    account_id: Optional[str] = None


class WeChatLoginPollRequest(BaseModel):
    """微信扫码登录轮询请求。"""

    session_key: str


class ChannelOnboardStartRequest(BaseModel):
    """渠道扫码接入启动请求。"""

    account_id: Optional[str] = None
    display_name: Optional[str] = None


class ChannelOnboardPollRequest(BaseModel):
    """渠道扫码接入轮询请求。"""

    session_key: str


def _mask_channel_secret(key: str, value: Any) -> Any:
    if value is None:
        return value
    lowered = key.lower()
    if lowered in {"token", "secret", "app_secret", "client_secret", "bot_id", "sendkey"}:
        text = str(value)
        if not text:
            return ""
        if lowered == "bot_id":
            return text[:8] + "..."
        if lowered == "token":
            return text[:10] + "..."
        return "***"
    if lowered in {"app_id", "client_id"}:
        text = str(value)
        return text[:8] + "..." if text else ""
    return value


def _normalize_accounts_payload(config_dict: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(config_dict)
    accounts = normalized.get("accounts", {}) or {}
    normalized["accounts"] = {
        str(account_id): {
            **dict(account_cfg),
            "account_id": str(account_id),
        }
        for account_id, account_cfg in accounts.items()
    }
    return normalized


def _current_owner_id() -> Optional[str]:
    """当前请求的数据归属：管理员为 None，普通用户为其 user id。"""
    from backend.modules.multiuser.permissions import get_request_user

    user = get_request_user()
    if user is None or getattr(user, "is_admin", False):
        return None
    return getattr(user, "owner_id", None)


def _owned_accounts(channel_config: Any, owner_id: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """只保留当前归属的扩展账号；管理员归属为 None。"""
    accounts = _normalize_accounts_payload(channel_config.model_dump()).get("accounts", {}) or {}
    target = str(owner_id or "")
    return {
        str(account_id): dict(account_cfg)
        for account_id, account_cfg in accounts.items()
        if str(account_cfg.get("owner_id") or "") == target
    }


def _channel_view_for_owner(channel_config: Any, owner_id: Optional[str]) -> Any:
    """把全局渠道配置裁剪成当前用户可见的视图。

    管理员：顶层配置即主账号，附加 owner_id 为空的扩展账号。
    普通用户：自己的第一个账号提升为顶层，其余账号留在 accounts。
    """
    owned = _owned_accounts(channel_config, owner_id)
    if owner_id is None:
        data = channel_config.model_dump()
        data["accounts"] = owned
        return channel_config.__class__(**data)

    if not owned:
        view = channel_config.__class__()
        view.enabled = False
        view.accounts = {}
        return view

    first_id = sorted(owned)[0]
    data = channel_config.__class__().model_dump()
    data.update(owned[first_id])
    data["account_id"] = first_id
    data["owner_id"] = owner_id
    data["enabled"] = bool(owned[first_id].get("enabled"))
    data["accounts"] = {
        account_id: account_cfg
        for account_id, account_cfg in owned.items()
        if account_id != first_id
    }
    return channel_config.__class__(**data)


def _owned_account_ids(channel_config: Any, owner_id: Optional[str]) -> set[str]:
    """当前用户可操作的账号 ID 集合。"""
    ids = set(_owned_accounts(channel_config, owner_id))
    if owner_id is None:
        ids.add(str(getattr(channel_config, "account_id", "default") or "default"))
    return ids


def _merge_owned_channel_config(
    channel_config: Any,
    payload: Dict[str, Any],
    owner_id: Optional[str],
    config_class: Any,
) -> Any:
    """把当前用户提交的账号合并回全局配置，保留其他归属的账号。"""
    existing = _normalize_accounts_payload(channel_config.model_dump())
    payload = dict(payload or {})
    payload_accounts = payload.pop("accounts", {}) or {}

    top_id = str(payload.get("account_id") or "default").strip() or "default"
    incoming: Dict[str, Dict[str, Any]] = {
        top_id: {**payload, "account_id": top_id, "owner_id": owner_id}
    }
    for raw_id, account_cfg in payload_accounts.items():
        account_id = str(raw_id or "default").strip() or "default"
        incoming[account_id] = {
            **dict(account_cfg or {}),
            "account_id": account_id,
            "owner_id": owner_id,
        }

    target_owner = str(owner_id or "")
    accounts = {
        str(account_id): dict(account_cfg)
        for account_id, account_cfg in (existing.get("accounts") or {}).items()
        if str(account_cfg.get("owner_id") or "") != target_owner
    }

    reserved = set(accounts)
    if owner_id is not None:
        # 普通用户不能占用管理员主账号的 ID
        reserved.add(str(existing.get("account_id") or "default"))

    for account_id, account_cfg in incoming.items():
        final_id = account_id
        if final_id in reserved:
            final_id = f"u_{(owner_id or '')[:8]}_{account_id}"
            while final_id in reserved:
                final_id += "_1"
        reserved.add(final_id)
        accounts[final_id] = {**account_cfg, "account_id": final_id}

    existing["accounts"] = accounts
    if owner_id is None:
        # 只有管理员能改顶层主账号配置
        existing.update({key: value for key, value in payload.items() if key != "accounts"})
        existing["owner_id"] = None
    return config_class(**existing)


def _serialize_channel_for_list(channel_config: Any) -> Dict[str, Any]:
    config_dict = _normalize_accounts_payload(channel_config.model_dump())
    accounts = config_dict.get("accounts", {}) or {}
    enabled = bool(config_dict.get("enabled")) or any(
        bool(account_cfg.get("enabled"))
        for account_cfg in accounts.values()
    )
    visible_config = {
        key: _mask_channel_secret(key, value)
        for key, value in config_dict.items()
        if key != "accounts"
    }
    visible_accounts = {
        account_id: {
            key: _mask_channel_secret(key, value)
            for key, value in account_cfg.items()
        }
        for account_id, account_cfg in accounts.items()
    }

    return {
        "enabled": enabled,
        "configured": any(
            bool(account_cfg.get(field))
            for account_cfg in [config_dict, *accounts.values()]
            for field in ("token", "app_id", "client_id", "bot_id", "endpoint", "sendkey")
        ),
        "config": {
            **visible_config,
            "accounts": visible_accounts,
            "account_count": (1 if any(config_dict.get(field) for field in ("token", "app_id", "client_id", "bot_id", "endpoint", "sendkey")) else 0) + len(visible_accounts),
        },
    }


def _select_account_config(channel_config: Any, account_id: Optional[str]) -> Any:
    config_dict = _normalize_accounts_payload(channel_config.model_dump())
    selected_account_id = str(account_id or config_dict.get("account_id") or "default")
    top_level_account_id = str(config_dict.get("account_id") or "default")
    accounts = config_dict.get("accounts", {}) or {}

    if selected_account_id == top_level_account_id:
        return channel_config.__class__(**{**config_dict, "accounts": {}, "account_id": top_level_account_id})

    account_cfg = accounts.get(selected_account_id)
    if account_cfg is None:
        if accounts:
            raise ValueError(f"机器人账号不存在: {selected_account_id}")
        return channel_config.__class__(**{**config_dict, "accounts": {}, "account_id": selected_account_id})

    merged_data = {
        **config_dict,
        **account_cfg,
        "accounts": {},
        "account_id": selected_account_id,
    }
    return channel_config.__class__(**merged_data)


_CHANNEL_UNIQUE_ID_FIELDS: Dict[str, tuple[str, ...]] = {
    "telegram": ("token",),
    "qq": ("app_id",),
    "wechat": ("login_bot_id",),
    "dingtalk": ("client_id",),
    "feishu": ("app_id",),
    "weibo": ("app_id",),
    "wecom": ("bot_id",),
    "serverchan": ("sendkey",),
}


# 支持主动推送的渠道（与 ChannelManager 实际可投递的渠道保持一致）
_DELIVERY_CHANNEL_IDS = (
    "telegram",
    "qq",
    "wechat",
    "dingtalk",
    "feishu",
    "weibo",
    "wecom",
    "discord",
    "serverchan",
)

# 渠道标识形如 wecom / feishu，用于把普通会话名与渠道会话名区分开
_CHANNEL_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]{1,20}")

_DELIVERY_CHANNEL_LABELS = {
    "telegram": "Telegram",
    "qq": "QQ",
    "wechat": "微信",
    "dingtalk": "钉钉",
    "feishu": "飞书",
    "weibo": "微博",
    "wecom": "企业微信",
    "discord": "Discord",
    "serverchan": "Server酱",
}


def _is_group_chat_id(channel: str, chat_id: str) -> bool:
    """判断 chat_id 是否为群（与 cron executor 的判断保持一致）。"""
    if channel == "feishu":
        return str(chat_id).startswith("oc_")
    return False


def _parse_session_route(session_name: str) -> Optional[tuple[str, str, str]]:
    """从渠道会话名解析推送目标，首段须为合法渠道标识。"""
    parts = (session_name or "").split(":")
    if len(parts) < 3:
        return None
    channel, account_id, chat_id = parts[0], parts[1], parts[2]
    if not _CHANNEL_ID_PATTERN.fullmatch(channel) or not chat_id:
        return None
    return channel, account_id or "default", chat_id


async def _collect_channel_chats(
    channel_ids: tuple[str, ...],
    per_channel_limit: int = 100,
    owner_id: Optional[str] = None,
) -> Dict[str, list[Dict[str, Any]]]:
    """按会话名前缀反查历史渠道会话的 chat_id，并按 owner_id 过滤。"""
    from sqlalchemy import select

    from backend.database import get_db_session_factory
    from backend.models.session import Session as SessionModel
    from backend.utils.datetime_utils import to_utc_iso

    grouped: Dict[str, Dict[tuple[str, str], Dict[str, Any]]] = {
        channel_id: {} for channel_id in channel_ids
    }

    try:
        db_factory = get_db_session_factory()
    except Exception as e:
        logger.warning(f"Database unavailable for delivery targets: {e}")
        return {channel_id: [] for channel_id in channel_ids}

    async with db_factory() as db:
        for channel_id in channel_ids:
            escaped = (
                channel_id.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            query = select(SessionModel).where(
                SessionModel.name.like(f"{escaped}:%", escape="\\")
            )
            if owner_id is None:
                query = query.where(SessionModel.owner_id.is_(None))
            else:
                query = query.where(SessionModel.owner_id == owner_id)
            result = await db.execute(
                query.order_by(SessionModel.updated_at.desc()).limit(per_channel_limit)
            )
            for session in result.scalars().all():
                route = _parse_session_route(session.name)
                if not route or route[0] != channel_id:
                    continue
                _, account_id, chat_id = route
                key = (account_id, chat_id)
                if key in grouped[channel_id]:
                    continue
                grouped[channel_id][key] = {
                    "chat_id": chat_id,
                    "account_id": account_id,
                    "is_group": _is_group_chat_id(channel_id, chat_id),
                    "session_id": session.id,
                    "session_name": session.name,
                    "last_used": to_utc_iso(session.updated_at),
                }

    return {
        channel_id: sorted(
            grouped[channel_id].values(),
            key=lambda item: item.get("last_used") or "",
            reverse=True,
        )
        for channel_id in channel_ids
    }


def _validate_duplicate_accounts(channel_name: str, channel_config: Any) -> None:
    """校验多机器人配置中是否复用了同一物理机器人身份。"""
    unique_fields = _CHANNEL_UNIQUE_ID_FIELDS.get(channel_name)
    if not unique_fields:
        return

    config_dict = _normalize_accounts_payload(channel_config.model_dump())
    seen: Dict[str, str] = {}

    def build_signature(account_cfg: Dict[str, Any]) -> Optional[str]:
        parts = []
        for field in unique_fields:
            value = str(account_cfg.get(field) or "").strip()
            if not value:
                return None
            parts.append(f"{field}={value}")
        return "|".join(parts)

    accounts_to_check = [
        (str(config_dict.get("account_id") or "default"), config_dict),
        *[
            (str(account_id), dict(account_cfg))
            for account_id, account_cfg in (config_dict.get("accounts", {}) or {}).items()
        ],
    ]

    for account_id, account_cfg in accounts_to_check:
        signature = build_signature(account_cfg)
        if not signature:
            continue
        previous_account = seen.get(signature)
        if previous_account is not None:
            fields_text = ", ".join(unique_fields)
            raise ValueError(
                f"检测到重复机器人配置：账号 '{account_id}' 与 '{previous_account}' 使用相同的 {fields_text}。"
                "同一个物理机器人不能重复配置为多个账号。"
            )
        seen[signature] = account_id


def _validate_external_coding_route_config(channel_name: str, channel_config: Any) -> None:
    """校验渠道账号的外部编程工具路由配置。"""
    workspace = Path(config_loader.config.workspace.path).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    registry = ExternalAgentRegistry(workspace=workspace)

    config_dict = _normalize_accounts_payload(channel_config.model_dump())
    accounts_to_check = [
        (str(config_dict.get("account_id") or "default"), config_dict),
        *[
            (str(account_id), dict(account_cfg))
            for account_id, account_cfg in (config_dict.get("accounts", {}) or {}).items()
        ],
    ]

    for account_id, account_cfg in accounts_to_check:
        route_mode = str(account_cfg.get("routing_mode", "ai") or "ai").strip().lower()
        if route_mode not in {"ai", "direct"}:
            raise ValueError(
                f"{channel_name} 渠道账号 '{account_id}' 的路由模式无效: {route_mode}"
            )

        profile_name = str(account_cfg.get("external_coding_profile", "") or "").strip()
        if route_mode == "direct" and not profile_name:
            raise ValueError(
                f"{channel_name} 渠道账号 '{account_id}' 处于直通模式时，必须设置默认外部编程工具。"
            )

        if profile_name:
            try:
                registry.resolve_profile(profile_name)
            except Exception as exc:
                raise ValueError(
                    f"{channel_name} 渠道账号 '{account_id}' 的外部编程工具不可用: {exc}"
                ) from exc


def _apply_onboarding_credentials(
    channel_name: str,
    account_id: Optional[str],
    credentials: Dict[str, Any],
    display_name: str = "",
    owner_id: Optional[str] = None,
) -> Any:
    """把扫码凭据写入渠道配置并启用账号，不覆盖其他配置。"""
    from backend.modules.config.schema import (
        QQConfig,
        FeishuConfig,
        WeComConfig,
        DingTalkConfig,
        WeChatConfig,
    )

    config_classes = {
        "qq": QQConfig,
        "feishu": FeishuConfig,
        "wecom": WeComConfig,
        "dingtalk": DingTalkConfig,
        "wechat": WeChatConfig,
    }
    config_class = config_classes.get(channel_name)
    channel_config = getattr(config_loader.config.channels, channel_name, None)
    if config_class is None or channel_config is None:
        raise ValueError(f"渠道 {channel_name} 不支持扫码接入")

    config_data = channel_config.model_dump()
    top_level_account_id = str(config_data.get("account_id") or "default")
    target_account_id = str(account_id or top_level_account_id).strip() or top_level_account_id
    target_display_name = str(display_name or "").strip()
    accounts = dict(config_data.get("accounts") or {})

    # 管理员扫码到主账号时沿用顶层配置
    if owner_id is None and target_account_id == top_level_account_id:
        config_data.update(credentials)
        config_data["enabled"] = True
        if target_display_name and not str(config_data.get("display_name") or "").strip():
            config_data["display_name"] = target_display_name
        updated_config = config_class(**config_data)
        _validate_duplicate_accounts(channel_name, updated_config)
        _validate_external_coding_route_config(channel_name, updated_config)
        setattr(config_loader.config.channels, channel_name, updated_config)
        return updated_config, target_account_id

    owner_key = str(owner_id or "")
    reserved = {
        str(account_id_)
        for account_id_, account_cfg in accounts.items()
        if str(account_cfg.get("owner_id") or "") != owner_key
    }
    if owner_id is not None:
        reserved.add(top_level_account_id)

    final_account_id = target_account_id
    if final_account_id in reserved:
        if owner_id is None:
            raise ValueError(f"账号 ID 已被占用: {final_account_id}")
        final_account_id = f"u_{owner_id[:8]}_{target_account_id}"
        while final_account_id in reserved:
            final_account_id += "_1"

    account_data = dict(accounts.get(final_account_id) or {})
    account_data.update(credentials)
    account_data["account_id"] = final_account_id
    account_data["enabled"] = True
    account_data["owner_id"] = owner_id
    if target_display_name and not str(account_data.get("display_name") or "").strip():
        account_data["display_name"] = target_display_name
    accounts[final_account_id] = account_data
    config_data["accounts"] = accounts

    updated_config = config_class(**config_data)
    # 先校验再落盘：扫码到的机器人若已被其他账号占用，不应留下半写入配置。
    _validate_duplicate_accounts(channel_name, updated_config)
    _validate_external_coding_route_config(channel_name, updated_config)
    setattr(config_loader.config.channels, channel_name, updated_config)
    return updated_config, final_account_id


async def purge_owner_channel_accounts(owner_id: str, fastapi_request: Request) -> int:
    """删除某用户的全部渠道账号并热重载，供删除用户时调用。"""
    supported = [
        "telegram", "discord", "qq", "wechat", "dingtalk",
        "feishu", "weibo", "wecom", "xiaozhi", "serverchan",
    ]
    removed = 0
    for channel_id in supported:
        channel_config = getattr(config_loader.config.channels, channel_id, None)
        if channel_config is None:
            continue
        data = channel_config.model_dump()
        accounts = data.get("accounts") or {}
        kept = {
            account_id: account_cfg
            for account_id, account_cfg in accounts.items()
            if str(account_cfg.get("owner_id") or "") != owner_id
        }
        if len(kept) == len(accounts):
            continue
        removed += len(accounts) - len(kept)
        data["accounts"] = kept
        setattr(config_loader.config.channels, channel_id, channel_config.__class__(**data))

    if not removed:
        return 0

    await config_loader.save()
    message_handler = getattr(fastapi_request.app.state, "message_handler", None)
    if message_handler is not None and hasattr(message_handler, "reload_config"):
        message_handler.reload_config()
    channel_manager = await _restart_channel_manager(fastapi_request)
    if message_handler is not None and channel_manager is not None:
        message_handler.set_channel_manager(channel_manager)
    logger.info(f"Removed {removed} channel account(s) owned by user {owner_id}")
    return removed


async def _restart_channel_manager(fastapi_request: Request) -> Optional[ChannelManager]:
    """基于最新配置热重建渠道管理器。"""
    app_state = fastapi_request.app.state
    old_manager = getattr(app_state, "channel_manager", None)
    old_task = getattr(app_state, "channel_manager_task", None)
    message_queue = getattr(app_state, "message_queue", None)

    if message_queue is None:
        logger.warning("Skip channel manager reload: message_queue missing")
        return old_manager

    if old_manager is not None:
        await old_manager.stop_all()

    if old_task is not None:
        try:
            await asyncio.wait_for(old_task, timeout=5)
        except asyncio.TimeoutError:
            old_task.cancel()
            await asyncio.gather(old_task, return_exceptions=True)
        except asyncio.CancelledError:
            pass

    manager = ChannelManager(config_loader.config, message_queue)
    app_state.channel_manager = manager
    set_channel_manager(manager)

    message_handler = getattr(app_state, "message_handler", None)
    if message_handler is not None:
        message_handler.set_channel_manager(manager)

    cron_executor = getattr(app_state, "cron_executor", None)
    if cron_executor is not None:
        cron_executor.channel_manager = manager

    shared = getattr(app_state, "shared", None)
    if isinstance(shared, dict):
        tool_params = shared.get("tool_params")
        if isinstance(tool_params, dict):
            try:
                from backend.modules.tools.setup import register_all_tools

                tool_params["channel_manager"] = manager
                shared["tool_registry"] = register_all_tools(
                    **tool_params,
                    memory_store=shared.get("memory"),
                )
                cron_agent = getattr(cron_executor, "agent", None)
                if cron_agent is not None:
                    cron_agent.tools = register_all_tools(
                        **tool_params,
                        memory_store=shared.get("memory"),
                    )
                logger.info("Shared tool registry synced with reloaded channel manager")
            except Exception as exc:
                logger.warning(f"Failed to sync shared tool registry after channel reload: {exc}")

    background_tasks = getattr(app_state, "background_tasks", None)
    if isinstance(background_tasks, list) and old_task is not None:
        app_state.background_tasks = [
            task for task in background_tasks
            if task is not old_task and not task.done()
        ]
        background_tasks = app_state.background_tasks
    new_task = None
    if manager.enabled_channels:
        new_task = asyncio.create_task(manager.start_all())
        if isinstance(background_tasks, list):
            background_tasks.append(new_task)
    app_state.channel_manager_task = new_task

    logger.info(
        f"Reloaded channel manager with {len(manager.enabled_channels)} channel instance(s)"
    )
    return manager


@router.get("/list")
async def list_channels():
    """获取所有可用渠道列表"""
    try:
        config = config_loader.config
        channels_config = config.channels
        owner_id = _current_owner_id()
        
        telegram_data = _serialize_channel_for_list(_channel_view_for_owner(channels_config.telegram, owner_id))
        discord_data = _serialize_channel_for_list(_channel_view_for_owner(channels_config.discord, owner_id))
        qq_data = _serialize_channel_for_list(_channel_view_for_owner(channels_config.qq, owner_id))
        wechat_data = _serialize_channel_for_list(_channel_view_for_owner(channels_config.wechat, owner_id))
        dingtalk_data = _serialize_channel_for_list(_channel_view_for_owner(channels_config.dingtalk, owner_id))
        feishu_data = _serialize_channel_for_list(_channel_view_for_owner(channels_config.feishu, owner_id))
        weibo_data = _serialize_channel_for_list(_channel_view_for_owner(channels_config.weibo, owner_id))
        wecom_data = _serialize_channel_for_list(_channel_view_for_owner(channels_config.wecom, owner_id))
        xiaozhi_data = _serialize_channel_for_list(_channel_view_for_owner(channels_config.xiaozhi, owner_id))
        serverchan_data = _serialize_channel_for_list(_channel_view_for_owner(channels_config.serverchan, owner_id))

        available_channels = {
            "telegram": {
                "name": "Telegram",
                "description": "Telegram messaging platform",
                "icon": "telegram",
                **telegram_data,
            },
            "discord": {
                "name": "Discord",
                "description": "Discord messaging platform",
                "icon": "discord",
                **discord_data,
            },
            "qq": {
                "name": "QQ",
                "description": "QQ messaging platform",
                "icon": "qq",
                **qq_data,
            },
            "wechat": {
                "name": "微信",
                "description": "WeChat messaging platform",
                "icon": "wechat",
                **wechat_data,
            },
            "dingtalk": {
                "name": "钉钉",
                "description": "DingTalk messaging platform",
                "icon": "dingtalk",
                **dingtalk_data,
            },
            "feishu": {
                "name": "飞书",
                "description": "Feishu/Lark messaging platform",
                "icon": "feishu",
                **feishu_data,
            },
            "weibo": {
                "name": "微博",
                "description": "Weibo messaging platform",
                "icon": "weibo",
                **weibo_data,
            },
            "wecom": {
                "name": "企业微信",
                "description": "Enterprise WeChat messaging platform",
                "icon": "wecom",
                **wecom_data,
            },
            "xiaozhi": {
                "name": "小智AI",
                "description": "小智机器人 MCP 接入（工具调用/对话模式）",
                "icon": "xiaozhi",
                **xiaozhi_data,
            },
            "serverchan": {
                "name": "Server酱",
                "description": "Server酱 消息推送（微信 / Server酱³ App）",
                "icon": "serverchan",
                **serverchan_data,
            }
        }
        
        return {
            "success": True,
            "channels": available_channels
        }
    
    except Exception as e:
        logger.error(f"Error listing channels: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/delivery-targets")
async def get_delivery_targets():
    """获取已配置的渠道推送目标，含机器人账号与历史 chat_id。"""
    try:
        config = config_loader.config
        channels_config = config.channels
        owner_id = _current_owner_id()

        try:
            status_map = get_channel_manager().get_status()
        except Exception as exc:  # 渠道管理器未就绪时降级为只返回配置
            logger.debug(f"Channel status unavailable for delivery targets: {exc}")
            status_map = {}

        known_chats = await _collect_channel_chats(_DELIVERY_CHANNEL_IDS, owner_id=owner_id)

        targets: list[Dict[str, Any]] = []
        for channel_id in _DELIVERY_CHANNEL_IDS:
            channel_config = getattr(channels_config, channel_id, None)
            if channel_config is None:
                continue

            view = _channel_view_for_owner(channel_config, owner_id)
            serialized = _serialize_channel_for_list(view)
            channel_status = status_map.get(channel_id) or {}
            allowed_accounts = _owned_account_ids(channel_config, owner_id)
            status_instances = {
                account_id: instance
                for account_id, instance in (channel_status.get("instances") or {}).items()
                if account_id in allowed_accounts
            }
            # 未配置且未运行的渠道没有推送能力，不出现在候选里
            if not serialized["configured"] and not status_instances:
                continue

            accounts_map = serialized["config"].get("accounts", {}) or {}

            accounts: list[Dict[str, Any]] = []
            config_dict = view.model_dump()
            # 顶层配置本身也是一个机器人账号（多账号模式下同样需要出现在推送目标里）
            default_account_id = str(config_dict.get("account_id") or "default")
            default_instance = status_instances.get(default_account_id, {})
            top_level_configured = any(
                bool(config_dict.get(field))
                for field in ("token", "app_id", "client_id", "bot_id", "endpoint", "sendkey")
            )
            if top_level_configured or default_instance or not accounts_map:
                accounts.append(
                    {
                        "account_id": default_account_id,
                        "display_name": str(
                            config_dict.get("display_name")
                            or _DELIVERY_CHANNEL_LABELS.get(channel_id, channel_id)
                            or default_account_id
                        ),
                        "enabled": bool(config_dict.get("enabled", True)),
                        "running": bool(default_instance.get("running", False)),
                    }
                )

            for account_id, account_cfg in accounts_map.items():
                instance_status = status_instances.get(str(account_id), {})
                accounts.append(
                    {
                        "account_id": str(account_id),
                        "display_name": str(
                            account_cfg.get("display_name")
                            or instance_status.get("display_name")
                            or account_id
                        ),
                        "enabled": bool(account_cfg.get("enabled", True)),
                        "running": bool(instance_status.get("running", False)),
                    }
                )

            targets.append(
                {
                    "channel": channel_id,
                    "name": _DELIVERY_CHANNEL_LABELS.get(channel_id, channel_id),
                    "icon": channel_id,
                    "enabled": bool(serialized["enabled"]) or bool(channel_status.get("running")),
                    "configured": bool(serialized["configured"]),
                    "running": bool(channel_status.get("running", False)),
                    "accounts": accounts,
                    "chats": known_chats.get(channel_id, []),
                }
            )

        return {"success": True, "targets": targets}

    except Exception as e:
        logger.error(f"Error getting delivery targets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_channels_status():
    """获取所有渠道的运行状态"""
    try:
        manager = get_channel_manager()
        raw_status = manager.get_status()
        owner_id = _current_owner_id()
        channels_config = config_loader.config.channels

        status = {}
        for channel_id, info in raw_status.items():
            channel_config = getattr(channels_config, channel_id, None)
            allowed = _owned_account_ids(channel_config, owner_id) if channel_config else set()
            instances = {
                account_id: instance
                for account_id, instance in (info.get("instances") or {}).items()
                if account_id in allowed
            }
            status[channel_id] = {
                **info,
                "instances": instances,
                "enabled": bool(instances),
                "running": any(bool(item.get("running")) for item in instances.values()),
            }

        return {
            "success": True,
            "status": status,
            "running": manager.is_running
        }
    
    except Exception as e:
        logger.error(f"Error getting channels status: {e}")
        return {
            "success": False,
            "status": {},
            "running": False,
            "error": str(e)
        }


@router.post("/test", dependencies=[Depends(require_admin)])
async def test_channel(request: ChannelTestRequest):
    """测试指定渠道的连接"""
    try:
        manager = get_channel_manager()
        account_id = str(request.account_id or "").strip() or None
        owner_id = _current_owner_id()
        
        if request.config:
            logger.info(
                f"Testing {request.channel} with temporary config"
                f"{f' for account {account_id}' if account_id else ''}"
            )
            
            # 创建临时配置对象
            from backend.modules.config.schema import (
                QQConfig, FeishuConfig, DingTalkConfig,
                TelegramConfig, DiscordConfig, WeChatConfig, WeiboConfig, WeComConfig,
                XiaozhiConfig, ServerChanConfig,
            )
            config_classes = {
                "qq": QQConfig,
                "feishu": FeishuConfig,
                "dingtalk": DingTalkConfig,
                "telegram": TelegramConfig,
                "discord": DiscordConfig,
                "wechat": WeChatConfig,
                "weibo": WeiboConfig,
                "wecom": WeComConfig,
                "xiaozhi": XiaozhiConfig,
                "serverchan": ServerChanConfig,
            }

            if request.channel not in config_classes:
                return {
                    "success": False,
                    "message": f"不支持的渠道: {request.channel}"
                }

            temp_channel_config = config_classes[request.channel](
                **_normalize_accounts_payload(request.config)
            )
            _validate_duplicate_accounts(request.channel, temp_channel_config)
            temp_config = _select_account_config(temp_channel_config, account_id)

            from backend.modules.channels.qq import QQChannel
            from backend.modules.channels.feishu import FeishuChannel
            from backend.modules.channels.dingtalk import DingTalkChannel
            from backend.modules.channels.telegram import TelegramChannel
            from backend.modules.channels.wechat import WeChatChannel
            from backend.modules.channels.weibo import WeiboChannel
            from backend.modules.channels.wecom import WeComChannel
            from backend.modules.channels.xiaozhi import XiaozhiChannel
            from backend.modules.channels.serverchan import ServerChanChannel

            channel_classes = {
                "qq": QQChannel,
                "feishu": FeishuChannel,
                "dingtalk": DingTalkChannel,
                "telegram": TelegramChannel,
                "wechat": WeChatChannel,
                "weibo": WeiboChannel,
                "wecom": WeComChannel,
                "xiaozhi": XiaozhiChannel,
                "serverchan": ServerChanChannel,
            }
            
            if request.channel in channel_classes:
                temp_channel = channel_classes[request.channel](temp_config)
                result = await temp_channel.test_connection()
            else:
                return {
                    "success": False,
                    "message": f"渠道 {request.channel} 暂不支持测试功能"
                }
        else:
            # 使用已保存的配置测试；普通用户只能测自己的账号
            channel_config = getattr(config_loader.config.channels, request.channel, None)
            allowed = _owned_account_ids(channel_config, owner_id) if channel_config else set()
            if owner_id is not None and not account_id:
                account_id = sorted(allowed)[0] if allowed else None
            if owner_id is not None and (not account_id or account_id not in allowed):
                return {
                    "success": False,
                    "message": "账号不存在或无权操作",
                }
            result = await manager.test_channel(request.channel, account_id=account_id)
        
        # 翻译英文消息为中文
        message = result["message"]
        message_translations = {
            # QQ 渠道消息
            "App ID or Secret not configured": "App ID 或 Secret 未配置",
            "Invalid App ID format - App ID should be at least 8 characters": "App ID 格式无效 - 至少需要 8 个字符",
            "Invalid Secret format - Secret should be at least 16 characters": "Secret 格式无效 - 至少需要 16 个字符",
            "Invalid App ID format - QQ App ID should be numeric (e.g., 102848021234)": "App ID 格式无效 - QQ App ID 必须是纯数字（例如：102848021234）",
            "Invalid Secret format - Secret should contain only letters and numbers": "Secret 格式无效 - 只能包含字母和数字",
            "Configuration format validated successfully. Enable the channel to test the actual connection.": "配置格式验证通过。启用渠道后将进行实际连接测试。",
            "QQ credentials verified successfully - connection test passed": "QQ 凭据验证成功 - 连接测试通过",
            "Invalid App ID or Secret - credentials rejected by QQ": "App ID 或 Secret 无效 - QQ 拒绝了凭据",
            "Access denied - check your bot permissions at q.qq.com": "访问被拒绝 - 请在 q.qq.com 检查机器人权限",
            "Connection timeout - check your network connection or QQ API status": "连接超时 - 请检查网络连接或 QQ API 状态",
            "Network error - unable to reach QQ API": "网络错误 - 无法连接到 QQ API",
            "QQ SDK not installed. Run: pip install qq-botpy": "QQ SDK 未安装。运行: pip install qq-botpy",
            
            # 飞书渠道消息
            "App ID or App Secret not configured": "App ID 或 App Secret 未配置",
            "Invalid App ID format - Feishu App ID should start with 'cli_' (e.g., cli_a6d0...)": "App ID 格式无效 - 飞书 App ID 必须以 'cli_' 开头（例如：cli_a6d0...）",
            "Invalid App ID format - App ID is too short": "App ID 格式无效 - App ID 太短",
            "Invalid App Secret format - App Secret is too short": "App Secret 格式无效 - App Secret 太短",
            "Feishu credentials verified successfully - connection test passed": "飞书凭据验证成功 - 连接测试通过",
            "Invalid App ID or App Secret - credentials rejected by Feishu": "App ID 或 App Secret 无效 - 飞书拒绝了凭据",
            "Connection timeout - check your network connection": "连接超时 - 请检查网络连接",
            "Invalid App ID or App Secret - check your credentials at open.feishu.cn": "App ID 或 App Secret 无效 - 请在 open.feishu.cn 检查凭据",
            "Feishu SDK not installed. Run: pip install lark-oapi": "飞书 SDK 未安装。运行: pip install lark-oapi",
            
            # 钉钉渠道消息
            "Client ID or Client Secret not configured": "Client ID 或 Client Secret 未配置",
            "DingTalk SDK not installed": "钉钉 SDK 未安装",
            "DingTalk credentials verified successfully": "钉钉凭据验证成功",
            "Invalid Client ID or Client Secret": "Client ID 或 Client Secret 无效",
            
            # Telegram 渠道消息
            "Token not configured": "Token 未配置",
            "python-telegram-bot not installed": "python-telegram-bot 未安装",
            
            # 企业微信渠道消息
            "Bot ID or Secret not configured": "Bot ID 或 Secret 未配置",
            "Invalid Bot ID format - Bot ID should be at least 8 characters": "Bot ID 格式无效 - 至少需要 8 个字符",
            "Invalid Secret format - Secret should be at least 16 characters": "Secret 格式无效 - 至少需要 16 个字符",
            "Invalid Bot ID format - should contain only letters, numbers, hyphens and underscores": "Bot ID 格式无效 - 只能包含字母、数字、连字符和下划线",
            "Invalid Secret format - should contain only letters, numbers, hyphens and underscores": "Secret 格式无效 - 只能包含字母、数字、连字符和下划线",
            "Invalid WebSocket URL format - should start with ws:// or wss://": "WebSocket URL 格式无效 - 必须以 ws:// 或 wss:// 开头",
            "WeCom credentials verified successfully - connection test passed": "企业微信凭据验证成功 - 连接测试通过",
            "Invalid Bot ID or Secret - authentication failed (error code: 40001)": "Bot ID 或 Secret 无效 - 认证失败（错误码：40001）",
            "Invalid Bot ID or Secret - bot not found or disabled (error code: 40014)": "Bot ID 或 Secret 无效 - 机器人未找到或已禁用（错误码：40014）",
            "Invalid Bot ID - bot not found or incorrect format (error code: 93019)": "Bot ID 无效 - 机器人未找到或格式不正确（错误码：93019）",
            "Connection timeout - check your network connection or WeCom API status": "连接超时 - 请检查网络连接或企业微信 API 状态",
            "Invalid WebSocket URL - check the websocket_url configuration": "WebSocket URL 无效 - 请检查 websocket_url 配置",
            "Invalid response format from WeCom server": "企业微信服务器响应格式无效",
            "websockets library not installed. Run: pip install websockets": "websockets 库未安装。运行: pip install websockets",
        }
        
        # 翻译消息
        translated_message = message_translations.get(message, message)
        
        # 动态消息翻译（前缀匹配）
        if translated_message == message:
            if message.startswith("Connected to @"):
                bot_username = message[len("Connected to @"):]
                translated_message = f"已连接到 @{bot_username}"
            elif message.startswith("Connection failed:"):
                error_detail = message[len("Connection failed:"):].strip()
                # Flood control 友好提示
                import re
                flood_match = re.search(r"Flood control exceeded.*?Retry in (\d+)", error_detail)
                if flood_match:
                    seconds = int(flood_match.group(1))
                    minutes = seconds // 60
                    if minutes > 0:
                        translated_message = f"测试过于频繁，Telegram 暂时限制了请求，请 {minutes} 分钟后再试（不影响正常聊天）"
                    else:
                        translated_message = f"测试过于频繁，Telegram 暂时限制了请求，请 {seconds} 秒后再试（不影响正常聊天）"
                else:
                    translated_message = f"连接失败: {error_detail}"
            elif message.startswith("Invalid Bot ID or Secret - credentials rejected by WeCom:"):
                error_detail = message[len("Invalid Bot ID or Secret - credentials rejected by WeCom:"):].strip()
                translated_message = f"Bot ID 或 Secret 无效 - 企业微信拒绝了凭据: {error_detail}"
            elif message.startswith("Connection closed by server - check your Bot ID and Secret (code:"):
                import re
                code_match = re.search(r'\(code: (\w+)\)', message)
                if code_match:
                    code = code_match.group(1)
                    translated_message = f"服务器关闭连接 - 请检查 Bot ID 和 Secret（错误码：{code}）"
                else:
                    translated_message = "服务器关闭连接 - 请检查 Bot ID 和 Secret"
            elif message.startswith("Network error - unable to reach WeCom API:"):
                error_detail = message[len("Network error - unable to reach WeCom API:"):].strip()
                translated_message = f"网络错误 - 无法连接到企业微信 API: {error_detail}"
        
        # 翻译 note 字段
        if result.get("bot_info") and result["bot_info"].get("note"):
            note = result["bot_info"]["note"]
            note_translations = {
                "Full connection test will be performed when channel is enabled": "启用渠道后将进行完整连接测试",
                "Format check passed. Real connection test will be performed when channel is enabled.": "格式检查通过。启用渠道后将进行真实连接测试。",
                "Successfully obtained access token from Feishu API": "成功从飞书 API 获取访问令牌",
                "Successfully authenticated with QQ API": "成功通过 QQ API 认证",
                "Successfully authenticated with WeCom API": "成功通过企业微信 API 认证",
            }
            result["bot_info"]["note"] = note_translations.get(note, note)
        
        # 翻译 status 字段
        if result.get("bot_info") and result["bot_info"].get("status"):
            status = result["bot_info"]["status"]
            status_translations = {
                "configured": "已配置",
                "format_validated": "格式已验证",
                "credentials_verified": "凭据已验证",
                "connected": "已连接"
            }
            result["bot_info"]["status"] = status_translations.get(status, status)
        
        return {
            "success": result["success"],
            "message": translated_message,
            "data": result.get("bot_info")
        }
    
    except Exception as e:
        logger.error(f"Error testing channel {request.channel}: {e}")
        return {
            "success": False,
            "message": f"测试失败: {str(e)}"
        }


@router.post("/wechat/login/start", dependencies=[Depends(require_admin)])
async def start_wechat_login(request: WeChatLoginStartRequest):
    """启动微信扫码登录。"""
    try:
        from backend.modules.channels.wechat import start_wechat_qr_login
        from backend.modules.config.schema import WeChatConfig

        channel_config = WeChatConfig(
            **_normalize_accounts_payload(
                request.config
                or _channel_view_for_owner(
                    config_loader.config.channels.wechat,
                    _current_owner_id(),
                ).model_dump()
            )
        )
        account_id = str(request.account_id or "default").strip() or "default"
        owner_id = _current_owner_id()
        if owner_id is not None:
            owned = _owned_account_ids(config_loader.config.channels.wechat, owner_id)
            if account_id not in owned:
                account_id = f"user_{owner_id[:8]}"
        resolved_config = _select_account_config(channel_config, account_id)

        result = await start_wechat_qr_login(
            account_id=account_id,
            base_url=str(getattr(resolved_config, "base_url", "") or ""),
            config_snapshot=channel_config.model_dump(),
        )
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"Failed to start wechat login: {e}")
        return {"success": False, "message": f"启动微信扫码登录失败: {e}"}


@router.post("/wechat/login/poll", dependencies=[Depends(require_admin)])
async def poll_wechat_login(request: WeChatLoginPollRequest, fastapi_request: Request):
    """轮询微信扫码登录状态。"""
    try:
        from backend.modules.channels.wechat import (
            clear_wechat_session_pause,
            poll_wechat_qr_login,
        )
        result = await poll_wechat_qr_login(request.session_key)
        if not result.get("success") or result.get("status") != "confirmed":
            return result

        login_data = dict(result.get("result") or {})
        owner_id = _current_owner_id()
        try:
            updated_config, account_id = _apply_onboarding_credentials(
                "wechat",
                result.get("account_id"),
                login_data,
                owner_id=owner_id,
            )
            await config_loader.save()
        except ValueError as exc:
            return {"success": False, "status": "error", "message": str(exc)}

        clear_wechat_session_pause(account_id)

        message_handler = getattr(fastapi_request.app.state, "message_handler", None)
        channel_manager = await _restart_channel_manager(fastapi_request)
        if message_handler is not None and channel_manager is not None:
            message_handler.set_channel_manager(channel_manager)

        return {
            "success": True,
            "status": "confirmed",
            "message": "微信连接成功",
            "account_id": account_id,
            "result": login_data,
            "config": _normalize_accounts_payload(
                _channel_view_for_owner(updated_config, owner_id).model_dump()
            ),
        }
    except Exception as e:
        logger.error(f"Failed to poll wechat login: {e}")
        return {"success": False, "message": f"轮询微信登录状态失败: {e}"}



@router.post("/{channel}/onboard/start", dependencies=[Depends(require_admin)])
async def start_channel_onboarding(channel: str, request: ChannelOnboardStartRequest):
    """发起 QQ / 飞书 / 企业微信 / 钉钉扫码接入，返回二维码。"""
    try:
        normalized = str(channel or "").strip().lower()
        if not supports_onboarding(normalized):
            return {"success": False, "message": f"渠道 {channel} 不支持扫码接入"}

        channel_config = getattr(config_loader.config.channels, normalized, None)
        if channel_config is None:
            return {"success": False, "message": f"渠道 {channel} 配置不存在"}

        account_id = str(
            request.account_id or getattr(channel_config, "account_id", "default") or "default"
        ).strip() or "default"
        owner_id = _current_owner_id()
        if owner_id is not None:
            owned = _owned_account_ids(channel_config, owner_id)
            if account_id not in owned:
                account_id = f"user_{owner_id[:8]}"
        result = await begin_onboarding(
            normalized,
            account_id,
            display_name=str(request.display_name or ""),
        )
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"Failed to start {channel} onboarding: {e}")
        return {"success": False, "message": f"发起扫码绑定失败: {e}"}


@router.post("/{channel}/onboard/poll", dependencies=[Depends(require_admin)])
async def poll_channel_onboarding(
    channel: str,
    request: ChannelOnboardPollRequest,
    fastapi_request: Request,
):
    """轮询扫码结果；成功后自动保存凭据、启用账号并热重启渠道。"""
    normalized = str(channel or "").strip().lower()
    if not supports_onboarding(normalized):
        return {"success": False, "status": "error", "message": f"渠道 {channel} 不支持扫码接入"}

    try:
        result = await poll_onboarding(request.session_key)
    except Exception as e:
        logger.error(f"Failed to poll {channel} onboarding: {e}")
        return {"success": False, "status": "error", "message": f"查询扫码状态失败: {e}"}

    status = str(result.get("status") or "pending")
    if status != "success":
        return {"success": status == "pending", **result}

    credentials = result.get("credentials") or {}
    if not credentials:
        return {"success": False, "status": "error", "message": "扫码成功但未返回机器人凭据"}

    try:
        owner_id = _current_owner_id()
        updated_config, account_id = _apply_onboarding_credentials(
            normalized,
            result.get("account_id"),
            credentials,
            display_name=str(result.get("display_name") or ""),
            owner_id=owner_id,
        )
        await config_loader.save()
    except ValueError as e:
        return {"success": False, "status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"Failed to persist {channel} onboarding credentials: {e}")
        return {"success": False, "status": "error", "message": f"保存机器人凭据失败: {e}"}

    message_handler = getattr(fastapi_request.app.state, "message_handler", None)
    try:
        if message_handler is not None and hasattr(message_handler, "reload_config"):
            message_handler.reload_config()
        channel_manager = await _restart_channel_manager(fastapi_request)
        if message_handler is not None and channel_manager is not None:
            message_handler.set_channel_manager(channel_manager)
    except Exception as e:
        logger.warning(f"Failed to reload channels after {channel} onboarding: {e}")

    logger.info(f"{channel} bot bound via QR onboarding: {account_id}")
    return {
        "success": True,
        "status": "success",
        "message": str(result.get("message") or "扫码绑定成功"),
        "account_id": account_id,
        "config": _normalize_accounts_payload(
            _channel_view_for_owner(updated_config, owner_id).model_dump()
        ),
    }


@router.post("/{channel}/onboard/cancel", dependencies=[Depends(require_admin)])
async def cancel_channel_onboarding(channel: str, request: ChannelOnboardPollRequest):
    """关闭二维码时释放扫码会话，避免后台继续保留轮询状态。"""
    if not supports_onboarding(str(channel or "").strip().lower()):
        return {"success": False, "message": f"渠道 {channel} 不支持扫码接入"}
    drop_onboarding_session(request.session_key)
    return {"success": True}


@router.post("/update", dependencies=[Depends(require_admin)])
async def update_channel_config(request: ChannelConfigUpdate, fastapi_request: Request):
    """更新渠道配置"""
    try:
        config = config_loader.config
        
        # 支持的渠道列表
        supported_channels = ["telegram", "discord", "qq", "wechat", "dingtalk", "feishu", "weibo", "wecom", "xiaozhi", "serverchan"]
        
        if request.channel not in supported_channels:
            raise HTTPException(status_code=400, detail=f"Unknown channel: {request.channel}")
        
        channel_config = getattr(config.channels, request.channel, None)
        if not channel_config:
            raise HTTPException(status_code=404, detail=f"Channel configuration not found: {request.channel}")

        from backend.modules.config.schema import (
            TelegramConfig, DiscordConfig, QQConfig,
            WeChatConfig, DingTalkConfig, FeishuConfig, WeiboConfig, WeComConfig, XiaozhiConfig,
            ServerChanConfig,
        )

        config_classes = {
            "telegram": TelegramConfig,
            "discord": DiscordConfig,
            "qq": QQConfig,
            "wechat": WeChatConfig,
            "dingtalk": DingTalkConfig,
            "feishu": FeishuConfig,
            "weibo": WeiboConfig,
            "wecom": WeComConfig,
            "xiaozhi": XiaozhiConfig,
            "serverchan": ServerChanConfig,
        }

        owner_id = _current_owner_id()
        updated_channel_config = _merge_owned_channel_config(
            channel_config,
            request.config,
            owner_id,
            config_classes[request.channel],
        )
        # 先校验再写回运行时配置，避免校验失败时内存中的配置已被污染
        _validate_duplicate_accounts(request.channel, updated_channel_config)
        _validate_external_coding_route_config(request.channel, updated_channel_config)
        setattr(config.channels, request.channel, updated_channel_config)
        
        # 保存配置
        await config_loader.save()
        
        # 重新加载配置到 message_handler
        try:
            if hasattr(fastapi_request.app.state, 'message_handler'):
                message_handler = fastapi_request.app.state.message_handler
                message_handler.reload_config()
                channel_manager = await _restart_channel_manager(fastapi_request)
                if channel_manager is not None:
                    message_handler.set_channel_manager(channel_manager)
                logger.info(
                    f"Reloaded message handler and channel manager after updating {request.channel}"
                )
        except Exception as e:
            logger.warning(f"Failed to reload message handler/channel manager config: {e}")
        
        logger.info(f"Updated {request.channel} channel configuration")
        
        return {
            "success": True,
            "message": f"{request.channel} configuration updated successfully"
        }
    
    except HTTPException:
        raise
    except ValueError as e:
        # 配置校验失败属于用户输入错误，返回 400 而不是 500
        logger.warning(f"Invalid channel config: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating channel config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{channel}/config")
async def get_channel_config(channel: str):
    """获取指定渠道的配置"""
    try:
        config = config_loader.config
        
        # 支持的渠道列表
        supported_channels = ["telegram", "discord", "qq", "wechat", "dingtalk", "feishu", "weibo", "wecom", "xiaozhi", "serverchan"]

        if channel not in supported_channels:
            raise HTTPException(status_code=404, detail=f"Channel not found: {channel}")

        channel_config = getattr(config.channels, channel, None)

        if not channel_config:
            logger.warning(f"Channel configuration not found for {channel}, creating default")
            from backend.modules.config.schema import (
                TelegramConfig, DiscordConfig, QQConfig, WeChatConfig,
                DingTalkConfig, FeishuConfig, WeiboConfig, WeComConfig, XiaozhiConfig,
                ServerChanConfig,
            )
            config_classes = {
                "telegram": TelegramConfig, "discord": DiscordConfig,
                "qq": QQConfig, "wechat": WeChatConfig, "dingtalk": DingTalkConfig,
                "feishu": FeishuConfig, "weibo": WeiboConfig,
                "wecom": WeComConfig, "xiaozhi": XiaozhiConfig,
                "serverchan": ServerChanConfig,
            }
            channel_config = config_classes[channel]()
            setattr(config.channels, channel, channel_config)
            await config_loader.save()

        owner_id = _current_owner_id()
        config_dict = _normalize_accounts_payload(
            _channel_view_for_owner(channel_config, owner_id).model_dump()
        )
        
        return {
            "success": True,
            "config": config_dict
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting channel config: {e}")
        raise HTTPException(status_code=500, detail=str(e))
