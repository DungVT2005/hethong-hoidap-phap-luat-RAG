"""
Định nghĩa các Pydantic Schemas cho JSON request và response của API,
khớp 100% với contract trong frontend/app.js và tương thích cả Pydantic v1 lẫn v2.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field

try:
    from pydantic import field_validator

    HAS_PYDANTIC_V2 = True
except ImportError:
    from pydantic import validator

    HAS_PYDANTIC_V2 = False


# ============================================================================
# AUTH SCHEMAS (/api/auth/*)
# ============================================================================
class LoginRequest(BaseModel):
    identifier: str = Field(..., min_length=1, description="Họ tên hoặc Email đăng nhập")
    password: str = Field(..., min_length=1, description="Mật khẩu")


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120, description="Họ và tên")
    email: str = Field(..., min_length=3, max_length=180, description="Địa chỉ Email")
    password: str = Field(..., min_length=8, max_length=128, description="Mật khẩu tối thiểu 8 ký tự")

    if HAS_PYDANTIC_V2:
        @field_validator("email")
        @classmethod
        def validate_email_format(cls, v: str) -> str:
            v = v.strip().lower()
            if "@" not in v or "." not in v.split("@")[-1]:
                raise ValueError("Địa chỉ email không hợp lệ.")
            return v
    else:
        @validator("email")
        def validate_email_format(cls, v: str) -> str:
            v = v.strip().lower()
            if "@" not in v or "." not in v.split("@")[-1]:
                raise ValueError("Địa chỉ email không hợp lệ.")
            return v


class ChangePasswordRequest(BaseModel):
    currentPassword: str = Field(..., min_length=1)
    newPassword: str = Field(..., min_length=8, description="Mật khẩu mới tối thiểu 8 ký tự")


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    status: bool
    createdAt: str


class AuthResponse(BaseModel):
    user: UserResponse
    token: str


# ============================================================================
# CHAT & RAG SCHEMAS (/api/questions, /api/history)
# ============================================================================
class QuestionRequest(BaseModel):
    content: str = Field(..., min_length=2, max_length=4000, description="Nội dung câu hỏi pháp luật")

    if HAS_PYDANTIC_V2:
        @field_validator("content")
        @classmethod
        def validate_content(cls, v: str) -> str:
            cleaned = v.strip()
            if len(cleaned) < 3:
                raise ValueError("Câu hỏi quá ngắn. Vui lòng nhập nội dung câu hỏi cụ thể hơn.")
            return cleaned
    else:
        @validator("content")
        def validate_content(cls, v: str) -> str:
            cleaned = v.strip()
            if len(cleaned) < 3:
                raise ValueError("Câu hỏi quá ngắn. Vui lòng nhập nội dung câu hỏi cụ thể hơn.")
            return cleaned


class SourceItemResponse(BaseModel):
    documentId: str
    chunkId: Optional[str] = None
    title: str
    article: str
    excerpt: str
    score: float
    rank: int


class QuestionItemResponse(BaseModel):
    id: str
    content: str
    status: str
    createdAt: str


class AnswerItemResponse(BaseModel):
    id: str
    content: str
    model: Optional[str] = None
    createdAt: str
    sources: list[SourceItemResponse] = Field(default_factory=list)


class ConversationResponse(BaseModel):
    id: str
    question: QuestionItemResponse
    answer: AnswerItemResponse


# ============================================================================
# ADMIN SCHEMAS (/api/admin/*)
# ============================================================================
class UpdateUserStatusRequest(BaseModel):
    status: bool


class DocumentResponse(BaseModel):
    id: str
    title: str
    type: str
    agency: str
    issueDate: str
    chunks: int
    fileName: Optional[str] = None
    createdAt: Optional[str] = None


class UploadDocumentResponse(BaseModel):
    message: str
    document: DocumentResponse
