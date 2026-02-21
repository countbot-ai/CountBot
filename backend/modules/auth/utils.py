"""认证工具函数 - 密码验证、token 管理"""

import hashlib
import secrets
import time
from typing import Optional

from loguru import logger


# ============================================================================
# 密码验证
# ============================================================================


def validate_password(password: str) -> tuple[bool, str]:
    """验证密码强度：至少8位，必须包含大写字母、小写字母和数字

    Returns:
        (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "密码至少8位"
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if not (has_upper and has_lower and has_digit):
        return False, "密码必须同时包含大写字母、小写字母和数字"
    return True, ""


def hash_password(password: str) -> str:
    """使用 SHA-256 + salt 哈希密码（避免额外依赖 bcrypt）"""
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}:{hashed}"


def verify_password(password: str, stored_hash: str) -> bool:
    """验证密码是否匹配"""
    if not stored_hash or ":" not in stored_hash:
        return False
    salt, expected_hash = stored_hash.split(":", 1)
    actual_hash = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return secrets.compare_digest(actual_hash, expected_hash)


# ============================================================================
# Session Token 管理
# ============================================================================

# 内存中的 session 存储: {token: {"username": str, "created_at": float}}
_sessions: dict[str, dict] = {}

# Token 有效期（秒）：24 小时
TOKEN_EXPIRY = 86400


def create_session(username: str) -> str:
    """创建新的 session token"""
    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "username": username,
        "created_at": time.time(),
    }
    # 清理过期 session
    _cleanup_expired()
    logger.info(f"Auth session created for user: {username}")
    return token


def validate_session(token: str) -> Optional[str]:
    """验证 session token，返回 username 或 None"""
    if not token:
        return None
    session = _sessions.get(token)
    if not session:
        return None
    if time.time() - session["created_at"] > TOKEN_EXPIRY:
        del _sessions[token]
        return None
    return session["username"]


def revoke_session(token: str) -> bool:
    """撤销 session"""
    if token in _sessions:
        del _sessions[token]
        return True
    return False


def _cleanup_expired():
    """清理过期 session"""
    now = time.time()
    expired = [t for t, s in _sessions.items() if now - s["created_at"] > TOKEN_EXPIRY]
    for t in expired:
        del _sessions[t]
