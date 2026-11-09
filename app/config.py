"""
Đọc và quản lý cấu hình hệ thống từ file .env và biến môi trường.
"""
from __future__ import annotations

import os
from pathlib import Path

# Tự động nạp file .env nếu có python-dotenv, hoặc đọc thủ công
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

try:
    from dotenv import load_dotenv
    if ENV_FILE.exists():
        load_dotenv(dotenv_path=ENV_FILE, override=False)
except ImportError:
    if ENV_FILE.exists():
        for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


def _get_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    """Lớp lưu trữ cấu hình toàn cục của ứng dụng."""

    def __init__(self) -> None:
        self.BASE_DIR: Path = BASE_DIR

        # Gemini API (Dùng để sinh câu trả lời RAG)
        self.GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
        self.GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
        self.GEMINI_TEMPERATURE: float = float(os.getenv("GEMINI_TEMPERATURE", "0.2"))
        self.GEMINI_MAX_OUTPUT_TOKENS: int = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "2048"))

        # Embedding: mặc định dùng "local" để tiết kiệm quota API AI
        self.EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "local").strip().lower()
        self.LOCAL_EMBEDDING_MODEL: str = os.getenv(
            "LOCAL_EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
        ).strip()
        self.GEMINI_EMBEDDING_MODEL: str = os.getenv(
            "GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"
        ).strip()
        self.ALLOW_EXTRACTIVE_FALLBACK: bool = _get_bool("ALLOW_EXTRACTIVE_FALLBACK", True)

        # SQLite & ChromaDB paths
        sqlite_rel = os.getenv("SQLITE_DB_PATH", "DB/legal_rag.db")
        schema_rel = os.getenv("SQLITE_SCHEMA_PATH", "DB/legal_rag_schema_sqlite.sql")
        chroma_rel = os.getenv("CHROMA_PERSIST_DIR", "chroma_db")

        self.SQLITE_DB_PATH: Path = (
            Path(sqlite_rel) if Path(sqlite_rel).is_absolute() else BASE_DIR / sqlite_rel
        )
        self.SQLITE_SCHEMA_PATH: Path = (
            Path(schema_rel) if Path(schema_rel).is_absolute() else BASE_DIR / schema_rel
        )
        self.CHROMA_PERSIST_DIR: Path = (
            Path(chroma_rel) if Path(chroma_rel).is_absolute() else BASE_DIR / chroma_rel
        )
        self.CHROMA_COLLECTION_NAME: str = os.getenv(
            "CHROMA_COLLECTION_NAME", "legal_chunks"
        ).strip()

        # Chunking & Retrieval
        self.CHUNK_MAX_CHARS: int = int(os.getenv("CHUNK_MAX_CHARS", "1200"))
        self.CHUNK_OVERLAP_CHARS: int = int(os.getenv("CHUNK_OVERLAP_CHARS", "200"))
        self.RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "5"))

        # JWT & Security
        self.JWT_SECRET_KEY: str = os.getenv(
            "JWT_SECRET_KEY", "luatai-super-secret-jwt-key-change-in-production-2026"
        )
        self.JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
        self.JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))
        self.MAX_FAILED_LOGIN_ATTEMPTS: int = int(os.getenv("MAX_FAILED_LOGIN_ATTEMPTS", "5"))
        self.LOCKOUT_DURATION_MINUTES: int = int(os.getenv("LOCKOUT_DURATION_MINUTES", "30"))

        # Seed defaults
        self.SEED_ADMIN_NAME: str = os.getenv("SEED_ADMIN_NAME", "Quản trị viên")
        self.SEED_ADMIN_EMAIL: str = os.getenv("SEED_ADMIN_EMAIL", "admin@example.com")
        self.SEED_ADMIN_PASSWORD: str = os.getenv("SEED_ADMIN_PASSWORD", "admin12345")
        self.SEED_USER_NAME: str = os.getenv("SEED_USER_NAME", "Nguyễn Văn A")
        self.SEED_USER_EMAIL: str = os.getenv("SEED_USER_EMAIL", "user@example.com")
        self.SEED_USER_PASSWORD: str = os.getenv("SEED_USER_PASSWORD", "user12345")
        self.SEED_SAMPLE_DOCS: bool = _get_bool("SEED_SAMPLE_DOCS", True)


settings = Settings()
