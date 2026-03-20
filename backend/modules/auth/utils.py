"""Authentication helpers for password hashing and remote auth sessions."""

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Optional, Tuple

from loguru import logger
from sqlalchemy import select


_AUTH_SESSION_PREFIX = "auth.session."

TOKEN_EXPIRY = 86400

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_KEY_LEN = 32
_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.@-]{3,32}$")


def validate_password(password: str) -> Tuple[bool, str]:
    """Validate password strength."""
    if len(password) < 8:
        return False, "密码至少8位"

    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)

    if not (has_upper and has_lower and has_digit):
        return False, "密码必须同时包含大写字母、小写字母和数字"

    return True, ""


def validate_username(username: str) -> Tuple[bool, str]:
    """Validate administrator username format."""
    normalized = username.strip()
    if not _USERNAME_PATTERN.fullmatch(normalized):
        return False, "账号只能包含字母、数字、点、下划线、@ 和中划线，长度 3-32 位"

    return True, ""


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def _legacy_sha256_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}:{hashed}"


def hash_password(password: str) -> str:
    """Hash password with scrypt."""
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_KEY_LEN,
    )
    return "$".join(
        [
            "scrypt",
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            _b64encode(salt),
            _b64encode(derived),
        ]
    )


def verify_password(password: str, stored_hash: str) -> bool:
    """Check whether the password matches the stored hash."""
    if not stored_hash:
        return False

    if stored_hash.startswith("scrypt$"):
        parts = stored_hash.split("$")
        if len(parts) != 6:
            return False

        _, n_value, r_value, p_value, salt_b64, expected_b64 = parts
        try:
            derived = hashlib.scrypt(
                password.encode("utf-8"),
                salt=_b64decode(salt_b64),
                n=int(n_value),
                r=int(r_value),
                p=int(p_value),
                dklen=_SCRYPT_KEY_LEN,
            )
        except (ValueError, TypeError):
            return False

        return hmac.compare_digest(_b64encode(derived), expected_b64)

    # Backward compatibility for legacy SHA-256 hashes. These should be rotated
    # on the next successful password change or bootstrap.
    if ":" in stored_hash:
        salt, expected_hash = stored_hash.split(":", 1)
        actual_hash = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
        return hmac.compare_digest(actual_hash, expected_hash)

    return False


def needs_password_rehash(stored_hash: str) -> bool:
    """Return whether the stored password hash should be upgraded."""
    return not stored_hash.startswith("scrypt$")


def _session_key(token: str) -> str:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"{_AUTH_SESSION_PREFIX}{token_hash}"


def _parse_session_value(raw_value: str) -> Optional[dict]:
    try:
        data = json.loads(raw_value)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    username = data.get("username")
    created_at = data.get("created_at")

    if not isinstance(username, str) or not username:
        return None

    try:
        created_at = float(created_at)
    except (TypeError, ValueError):
        return None

    return {"username": username, "created_at": created_at}


def _is_expired(session_data: dict, now: Optional[float] = None) -> bool:
    current_time = now if now is not None else time.time()
    return current_time - session_data["created_at"] > TOKEN_EXPIRY


def _cleanup_expired() -> None:
    """Remove expired or malformed auth sessions from persistent storage."""
    from backend.database import SessionLocal
    from backend.models.setting import Setting

    now = time.time()
    deleted = 0

    with SessionLocal() as db:
        result = db.execute(
            select(Setting).where(Setting.key.like(f"{_AUTH_SESSION_PREFIX}%"))
        )
        for setting in result.scalars().all():
            session_data = _parse_session_value(setting.value)
            if session_data is None or _is_expired(session_data, now):
                db.delete(setting)
                deleted += 1

        if deleted:
            db.commit()


def create_session(username: str) -> str:
    """Create a new persistent session token."""
    from backend.database import SessionLocal
    from backend.models.setting import Setting

    token = secrets.token_urlsafe(32)
    payload = json.dumps({"username": username, "created_at": time.time()})

    with SessionLocal() as db:
        db.merge(Setting(key=_session_key(token), value=payload))
        db.commit()

    _cleanup_expired()
    logger.info(f"Auth session created for user: {username}")
    return token


def validate_session(token: str) -> Optional[str]:
    """Validate a session token and return the username when valid."""
    if not token:
        return None

    from backend.database import SessionLocal
    from backend.models.setting import Setting

    with SessionLocal() as db:
        setting = db.get(Setting, _session_key(token))
        if setting is None:
            return None

        session_data = _parse_session_value(setting.value)
        if session_data is None or _is_expired(session_data):
            db.delete(setting)
            db.commit()
            return None

        return session_data["username"]


def revoke_session(token: str) -> bool:
    """Revoke a single session token."""
    if not token:
        return False

    from backend.database import SessionLocal
    from backend.models.setting import Setting

    with SessionLocal() as db:
        setting = db.get(Setting, _session_key(token))
        if setting is None:
            return False

        db.delete(setting)
        db.commit()
        return True


def revoke_all_sessions(username: Optional[str] = None) -> int:
    """Revoke all sessions, or all sessions owned by one user."""
    from backend.database import SessionLocal
    from backend.models.setting import Setting

    removed = 0
    now = time.time()

    with SessionLocal() as db:
        result = db.execute(
            select(Setting).where(Setting.key.like(f"{_AUTH_SESSION_PREFIX}%"))
        )
        for setting in result.scalars().all():
            session_data = _parse_session_value(setting.value)
            if session_data is None or _is_expired(session_data, now):
                db.delete(setting)
                removed += 1
                continue

            if username is None or session_data["username"] == username:
                db.delete(setting)
                removed += 1

        if removed:
            db.commit()

    return removed
