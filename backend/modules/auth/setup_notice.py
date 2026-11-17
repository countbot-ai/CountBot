"""远程首次初始化安全入口的启动提示：只把入口地址以横幅打到日志，secret 归 middleware 负责。"""

from __future__ import annotations

from loguru import logger

from backend.utils.network import get_local_ips
from backend.utils.runtime_env import (
    get_local_client_host,
    is_public_bind_host,
    resolve_bind_address,
)

FRAME_WIDTH = 68
ROW_INDENT = "  "
URL_INDENT = "    "
FRAME_CHAR = "="
SEPARATOR_CHAR = "-"


def _frame_row(text: str = "") -> str:
    """横幅内的一行，统一缩进并去掉行尾空白。"""
    return f"{ROW_INDENT}{text}".rstrip()


def resolve_setup_entry_base_urls() -> list[str]:
    """解析入口所在的服务地址。

    监听 0.0.0.0 / :: 时按本机网卡 IP 逐个给出，否则只给回环地址。
    检测不到网卡 IP 时退化为占位符，提示用户自行替换为服务器地址。
    """
    host, port = resolve_bind_address()
    if is_public_bind_host(host):
        local_ips = get_local_ips()
        if local_ips:
            return [f"http://{ip}:{port}" for ip in local_ips]
        return [f"http://YOUR_SERVER_IP:{port}"]
    return [f"http://{get_local_client_host(host)}:{port}"]


def build_setup_entry_urls(secret: str) -> list[str]:
    return [f"{base}/setup/{secret}" for base in resolve_setup_entry_base_urls()]


def build_setup_entry_notice(
    secret: str,
    ttl_minutes: int,
    *,
    urls: list[str] | None = None,
    refreshed: bool = False,
) -> str:
    """构建安全入口横幅文本。"""
    hosts, port = resolve_bind_address()
    entry_urls = urls if urls is not None else build_setup_entry_urls(secret)

    frame = FRAME_CHAR * FRAME_WIDTH
    separator = SEPARATOR_CHAR * FRAME_WIDTH

    title = "远程安全入口 / REMOTE SECURE ENTRY"
    if refreshed:
        title = f"{title}（已刷新 / REFRESHED）"

    lines = [frame, separator, _frame_row(title), separator, _frame_row()]

    if refreshed:
        lines.append(_frame_row("上一个入口已过期，请使用下面这个新入口。"))
        lines.append(_frame_row("The previous entry expired, use this new one."))
        lines.append(_frame_row())

    lines.append(_frame_row("请通过以下安全入口访问，防止未授权访问："))
    lines.append(_frame_row("Open the entry below to finish the first-time setup:"))
    lines.append(_frame_row())
    for url in entry_urls:
        lines.append(_frame_row(f"{URL_INDENT}{url}"))
    lines.append(_frame_row())
    lines.append(_frame_row(f"有效期 {ttl_minutes} 分钟，设置登录密码后此入口立即失效。"))
    lines.append(_frame_row("请勿截图或转发；一旦泄露，请重启服务获取新入口。"))

    if not is_public_bind_host(hosts):
        lines.append(_frame_row())
        lines.append(_frame_row(f"当前仅监听 {hosts}:{port}，远程访问请设置 COUNTBOT_HOST=0.0.0.0"))

    lines.extend([separator, frame])
    return "\n".join(lines)


def log_setup_entry_notice(
    secret: str,
    ttl_minutes: int,
    *,
    urls: list[str] | None = None,
    refreshed: bool = False,
) -> None:
    """以醒目横幅输出安全入口，避免被普通启动日志淹没。"""
    notice = build_setup_entry_notice(
        secret,
        ttl_minutes,
        urls=urls,
        refreshed=refreshed,
    )
    # 整块单条输出：控制台只有首行带时间戳，视觉上形成一个独立区块。
    logger.opt(colors=True).info(f"<yellow>{notice}</yellow>")
