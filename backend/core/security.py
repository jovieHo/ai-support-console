"""密码哈希和轻量签名令牌。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from core.config import get_settings


def hash_password(password: str) -> str:
    """使用 PBKDF2-SHA256 生成密码哈希。"""
    salt = hashlib.sha256(get_settings().secret_key.encode()).hexdigest()[:16]
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120000)
    return f"pbkdf2_sha256${salt}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, hashed_password: str) -> bool:
    """使用常量时间比较验证密码。"""
    return hmac.compare_digest(hash_password(password), hashed_password)


def create_access_token(subject: str, role: str, expires_minutes: int = 1440) -> str:
    """生成带过期时间的 HMAC-SHA256 签名令牌。"""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {"sub": subject, "role": role, "exp": int(expires_at.timestamp())}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    signature = hmac.new(
        get_settings().secret_key.encode(),
        body.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{body}.{signature}"


def decode_access_token(token: str) -> dict[str, str]:
    """验证签名和过期时间后返回令牌载荷。"""
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(
            get_settings().secret_key.encode(),
            body.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        payload = json.loads(base64.urlsafe_b64decode(body.encode()).decode())
        if int(payload["exp"]) < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("token expired")
        return payload
    except Exception as exc:
        raise ValueError("invalid token") from exc
