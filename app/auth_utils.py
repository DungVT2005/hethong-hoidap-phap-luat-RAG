"""
Tiện ích Bảo mật & Xác thực (AuthService theo sơ đồ lớp UML):
- Băm và kiểm tra mật khẩu bằng bcrypt (kèm fallback PBKDF2-HMAC-SHA256 chuẩn)
- Tạo và giải mã JWT (PyJWT chuẩn HS256, kèm fallback RFC 7519 HMAC-SHA256)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import settings

# Thử nạp thư viện bcrypt và PyJWT
try:
    import bcrypt as _bcrypt

    HAS_BCRYPT = True
except ImportError:
    _bcrypt = None
    HAS_BCRYPT = False

try:
    import jwt as _pyjwt

    HAS_PYJWT = True
except ImportError:
    _pyjwt = None
    HAS_PYJWT = False


def hash_password(plain_password: str) -> str:
    """Băm mật khẩu bằng bcrypt (hoặc PBKDF2-SHA256 nếu môi trường chưa cài bcrypt)."""
    password_bytes = plain_password.encode("utf-8")
    if HAS_BCRYPT and _bcrypt is not None:
        salt = _bcrypt.gensalt(rounds=12)
        return _bcrypt.hashpw(password_bytes, salt).decode("utf-8")

    # Fallback an toàn bằng PBKDF2-HMAC-SHA256
    salt_hex = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password_bytes, salt_hex.encode("utf-8"), 200_000)
    return f"pbkdf2_sha256${salt_hex}${dk.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Kiểm tra mật khẩu khớp với chuỗi băm trong CSDL."""
    if not plain_password or not hashed_password:
        return False

    if hashed_password.startswith("pbkdf2_sha256$"):
        try:
            _, salt_hex, stored_hex = hashed_password.split("$", 2)
            dk = hashlib.pbkdf2_hmac(
                "sha256",
                plain_password.encode("utf-8"),
                salt_hex.encode("utf-8"),
                200_000,
            )
            return hmac.compare_digest(dk.hex(), stored_hex)
        except Exception:
            return False

    if HAS_BCRYPT and _bcrypt is not None:
        try:
            return _bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        except Exception:
            return False

    return False


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode((segment + padding).encode("ascii"))


def create_access_token(
    user_id: str,
    email: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Tạo JWT token chứa thông tin định danh người dùng và vai trò."""
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES))
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    if HAS_PYJWT and _pyjwt is not None:
        token = _pyjwt.encode(
            payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
        )
        return token if isinstance(token, str) else token.decode("utf-8")

    # Chuẩn RFC 7519 HS256 JWT
    header = {"alg": "HS256", "typ": "JWT"}
    h_seg = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_seg = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h_seg}.{p_seg}".encode("ascii")
    sig = hmac.new(
        settings.JWT_SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    return f"{h_seg}.{p_seg}.{_b64url_encode(sig)}"


def decode_access_token(token: str) -> dict[str, Any]:
    """Giải mã và kiểm tra hạn sử dụng của JWT token."""
    if HAS_PYJWT and _pyjwt is not None:
        try:
            return _pyjwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
        except Exception as exc:
            raise ValueError(f"Token không hợp lệ hoặc đã hết hạn: {exc}") from exc

    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Định dạng token không hợp lệ.")
    h_seg, p_seg, s_seg = parts
    signing_input = f"{h_seg}.{p_seg}".encode("ascii")
    expected_sig = hmac.new(
        settings.JWT_SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    actual_sig = _b64url_decode(s_seg)
    if not hmac.compare_digest(expected_sig, actual_sig):
        raise ValueError("Chữ ký token không hợp lệ.")

    payload = json.loads(_b64url_decode(p_seg).decode("utf-8"))
    exp = payload.get("exp")
    if exp is not None and int(time.time()) > int(exp):
        raise ValueError("Phiên đăng nhập đã hết hạn.")
    return payload


class AuthService:
    """
    Lớp dịch vụ xác thực và phân quyền theo sơ đồ lớp UML (Class Diagram):
    - jwtSecret: String
    + authenticate(plain_password, hashed_password)
    + authorize(user_role, required_role)
    + validateToken(token)
    """

    def __init__(self, jwt_secret: str | None = None) -> None:
        self.jwtSecret = jwt_secret or settings.JWT_SECRET_KEY

    def authenticate(self, plain_password: str, hashed_password: str) -> bool:
        return verify_password(plain_password, hashed_password)

    def authorize(self, user_role: str, required_role: str = "ADMIN") -> bool:
        return (user_role or "").upper() == required_role.upper()

    def validateToken(self, token: str) -> dict[str, Any]:
        return decode_access_token(token)


auth_service = AuthService()
