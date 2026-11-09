"""
Router Xác thực & Tài khoản người dùng (/api/auth/*):
- POST /api/auth/login           : Đăng nhập (hỗ trợ khóa tài khoản khi sai mật khẩu quá số lần quy định)
- POST /api/auth/register        : Đăng ký tài khoản mới
- GET  /api/auth/me              : Lấy thông tin người dùng hiện tại từ JWT
- POST /api/auth/change-password : Đổi mật khẩu
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth_utils import create_access_token, hash_password, verify_password
from app.config import settings
from app.database import HAS_SQLALCHEMY, get_db
from app.dependencies import find_user_by_identifier, get_current_user
from app.mappers import map_user_to_dict
from app.models import User
from app.schemas import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Any = Depends(get_db)) -> dict[str, Any]:
    """
    Đăng nhập bằng Email hoặc Họ và tên.
    Nếu nhập sai mật khẩu quá MAX_FAILED_LOGIN_ATTEMPTS (mặc định 5 lần),
    hệ thống tự động khóa tài khoản (status = 0) theo đúng lưu đồ UML trang 14.
    """
    user = find_user_by_identifier(db, payload.identifier)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tài khoản hoặc mật khẩu không chính xác.",
        )

    if int(user.status) == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị khóa. Vui lòng liên hệ Quản trị viên để mở khóa.",
        )

    if not verify_password(payload.password, user.password_hash):
        attempts = int(user.failed_login_attempts or 0) + 1
        user.failed_login_attempts = attempts
        user.last_failed_login = _now_str()

        if attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
            user.status = 0
            db.add(user)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Tài khoản đã bị khóa do nhập sai mật khẩu quá "
                    f"{settings.MAX_FAILED_LOGIN_ATTEMPTS} lần."
                ),
            )

        db.add(user)
        db.commit()
        remaining = max(0, settings.MAX_FAILED_LOGIN_ATTEMPTS - attempts)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Mật khẩu không chính xác (còn {remaining} lần thử trước khi tài khoản bị khóa).",
        )

    # Đăng nhập thành công -> reset bộ đếm lỗi
    if user.failed_login_attempts or user.locked_until:
        user.failed_login_attempts = 0
        user.locked_until = None
        db.add(user)
        db.commit()

    token = create_access_token(
        user_id=user.user_id,
        email=user.email,
        role=user.role,
    )
    return {
        "user": map_user_to_dict(user),
        "token": token,
    }


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Any = Depends(get_db)) -> dict[str, Any]:
    """Đăng ký tài khoản người dùng mới (role = USER)."""
    email_clean = payload.email.strip().lower()
    name_clean = payload.name.strip()

    if HAS_SQLALCHEMY:
        existing = db.query(User).filter(User.email.ilike(email_clean)).first()
    else:
        existing = db.fetchone_dict(
            "SELECT user_id FROM users WHERE LOWER(email) = LOWER(?)", (email_clean,)
        )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Địa chỉ email này đã được đăng ký. Vui lòng sử dụng email khác.",
        )

    new_user = User(
        full_name=name_clean,
        email=email_clean,
        password_hash=hash_password(payload.password),
        role="USER",
        status=1,
    )
    db.add(new_user)
    db.commit()

    token = create_access_token(
        user_id=new_user.user_id,
        email=new_user.email,
        role=new_user.role,
    )
    return {
        "user": map_user_to_dict(new_user),
        "token": token,
    }


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Lấy thông tin người dùng hiện tại từ phiên đăng nhập."""
    return map_user_to_dict(current_user)


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> dict[str, str]:
    """Đổi mật khẩu cho người dùng đang đăng nhập."""
    if not verify_password(payload.currentPassword, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mật khẩu hiện tại không chính xác.",
        )

    if payload.currentPassword == payload.newPassword:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mật khẩu mới phải khác mật khẩu hiện tại.",
        )

    current_user.changePassword(hash_password(payload.newPassword))
    db.add(current_user)
    db.commit()
    return {"message": "Đã đổi mật khẩu thành công."}
