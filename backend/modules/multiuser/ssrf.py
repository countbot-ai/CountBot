"""出站 URL 安全校验（SSRF 防护）：仅 HTTPS，拒绝内网地址，解析后二次校验。"""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Iterable, Optional
from urllib.parse import urlparse

from loguru import logger


ALLOW_INSECURE_HTTP_ENV = "COUNTBOT_ALLOW_INSECURE_HTTP"
DEFAULT_ALLOWED_PORTS = (443,)


class SsrfError(ValueError):
    """URL 未通过安全校验。"""


def assert_outbound_url_allowed(
    url: str,
    *,
    allowed_hosts: Optional[Iterable[str]] = None,
    allowed_ports: Iterable[int] = DEFAULT_ALLOWED_PORTS,
    allow_http: Optional[bool] = None,
) -> str:
    """建连前重新校验目标地址，缩小配置期到使用期的 DNS 变更窗口。"""
    return validate_outbound_url(
        url,
        allowed_hosts=allowed_hosts,
        allowed_ports=allowed_ports,
        allow_http=allow_http,
    )


def _allow_http() -> bool:
    return os.getenv(ALLOW_INSECURE_HTTP_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    return any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
            # CGNAT 运营商级 NAT 网段 100.64.0.0/10
            (isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("100.64.0.0/10")),
        )
    )


def _resolve_host_ips(host: str) -> Iterable[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SsrfError(f"无法解析域名: {host}") from exc
    return {info[4][0] for info in infos}


def validate_outbound_url(
    url: str,
    *,
    allowed_hosts: Optional[Iterable[str]] = None,
    allowed_ports: Iterable[int] = DEFAULT_ALLOWED_PORTS,
    allow_http: Optional[bool] = None,
) -> str:
    """校验并返回规范化后的 URL；不合法直接抛 :class:`SsrfError`。"""
    raw = (url or "").strip()
    if not raw:
        raise SsrfError("URL 不能为空")

    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    sensitive = allow_http if allow_http is not None else _allow_http()
    if scheme == "https":
        pass
    elif scheme == "http" and sensitive:
        pass
    else:
        raise SsrfError("只允许 HTTPS 地址")

    if parsed.username or parsed.password:
        raise SsrfError("URL 不允许包含用户名或密码")

    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise SsrfError("URL 缺少主机名")

    if allowed_hosts is not None:
        normalized = {h.strip().lower() for h in allowed_hosts if h}
        if normalized and host not in normalized:
            raise SsrfError(f"域名不在允许清单内: {host}")

    port = parsed.port or (443 if scheme == "https" else 80)
    allowed_port_set = set(int(p) for p in allowed_ports)
    if allowed_port_set and port not in allowed_port_set:
        raise SsrfError(f"端口不被允许: {port}")

    # 字面量 IP 直接判断
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        if _is_blocked_ip(literal):
            raise SsrfError("禁止访问内网或保留地址")
    else:
        for resolved in _resolve_host_ips(host):
            try:
                ip = ipaddress.ip_address(resolved)
            except ValueError:
                continue
            if _is_blocked_ip(ip):
                logger.warning(f"Blocked outbound URL host {host} -> {resolved}")
                raise SsrfError("禁止访问内网或保留地址")

    return raw
