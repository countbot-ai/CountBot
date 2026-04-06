"""Helpers for startup environment variables."""

from __future__ import annotations

import os


DEFAULT_BIND_HOST = "127.0.0.1"
DEFAULT_BIND_PORT = 8000

COUNTBOT_HOST_ENV = "COUNTBOT_HOST"
COUNTBOT_PORT_ENV = "COUNTBOT_PORT"

PUBLIC_BIND_HOSTS = {"0.0.0.0", "::"}
LOCAL_CLIENT_HOSTS = {"", "0.0.0.0", "::", "127.0.0.1", "::1", "localhost"}


def resolve_bind_host(default: str = DEFAULT_BIND_HOST) -> str:
    value = os.getenv(COUNTBOT_HOST_ENV, "").strip()
    return value or default


def resolve_bind_port(default: int = DEFAULT_BIND_PORT) -> int:
    raw_value = os.getenv(COUNTBOT_PORT_ENV, "").strip()
    if not raw_value:
        return default

    try:
        port = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{COUNTBOT_PORT_ENV} must be an integer") from exc

    if not 1 <= port <= 65535:
        raise ValueError(f"{COUNTBOT_PORT_ENV} must be between 1 and 65535")

    return port


def resolve_bind_address(
    default_host: str = DEFAULT_BIND_HOST,
    default_port: int = DEFAULT_BIND_PORT,
) -> tuple[str, int]:
    return resolve_bind_host(default_host), resolve_bind_port(default_port)


def apply_bind_env(host: str, port: int) -> None:
    normalized_host = (host or DEFAULT_BIND_HOST).strip() or DEFAULT_BIND_HOST
    normalized_port = str(port)

    os.environ[COUNTBOT_HOST_ENV] = normalized_host
    os.environ[COUNTBOT_PORT_ENV] = normalized_port


def is_public_bind_host(host: str | None) -> bool:
    return (host or "").strip() in PUBLIC_BIND_HOSTS


def get_local_client_host(bind_host: str | None) -> str:
    normalized = (bind_host or "").strip()
    if normalized in LOCAL_CLIENT_HOSTS:
        return "localhost"
    return normalized
