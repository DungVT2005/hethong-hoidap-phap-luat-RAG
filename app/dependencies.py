"""
FastAPI Dependencies:
- Trích xuất Bearer token từ header Authorization
- Lấy người dùng hiện tại (get_current_user)
- Kiểm tra trạng thái tài khoản (status == 1, không bị khóa)
- Kiểm tra quyền Quản trị viên (require_admin)
"""
from __future__ import annotations

from typing import Any
from fastapi import Depends, Header, HTTPException, status

from app.auth_utils import decode_access_token
from app.database import HAS_SQLALCHEMY, get_db
from app.models import User


def find_user_by_id(db: Any, user_id: str) -> User | None:
    """Tìm User theo user_id trên cả SQLAlchemy Session hoặc FallbackSQLiteSession."""
    if HAS_SQLALCHEMY:
        return db.query(User).filter(User.user_id == user_id).first()
    row = db.fetchone_dict("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return User(**row) if row else None


def find_user_by_identifier(db: Any, identifier: str) -> User | None:
    """Tìm User theo email hoặc họ tên (full_name)."""
    ident = identifier.strip()
    if HAS_SQLALCHEMY:
        user = db.query(User).filter(User.email.ilike(ident)).first()
        if not user:
            user = db.query(User).filter(User.full_name == ident).first()
        return user

    row = db.fetchone_dict(
        "SELECT * FROM users WHERE LOWER(email) = LOWER(?) OR full_name = ? LIMIT 1",
        (ident, ident),
    )
    return User(**row) if row else None


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Any = Depends(get_db),
) -> User:
    """Dependency xác thực JWT token và trả về đối tượng User hiện tại."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Vui lòng đăng nhập để tiếp tục.",
        )

    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ.",
        )

    user = find_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Không tìm thấy tài khoản người dùng.",
        )

    if int(user.status) == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị khóa",
        )

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency kiểm tra người dùng hiện tại có vai trò ADMIN hay không."""
    if (current_user.role or "").upper() != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Quản trị viên (ADMIN) mới có quyền thực hiện thao tác này.",
        )
    return current_user
