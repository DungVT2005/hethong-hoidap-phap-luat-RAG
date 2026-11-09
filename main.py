"""
Điểm khởi động ứng dụng FastAPI (main.py):
- Tự động khởi tạo CSDL SQLite từ `DB/legal_rag_schema_sqlite.sql` (8 bảng, index, trigger)
- Tự động seed tài khoản Admin/User mặc định và nạp/chuẩn hóa văn bản pháp luật trong `lifespan`
  (không chạy ở thời điểm import module để tránh treo SpawnProcess trên Windows).
- Đăng ký các API routers: `/api/auth/*`, `/api/questions`, `/api/history`, `/api/admin/*`
- Phục vụ trực tiếp giao diện `frontend/` (index.html, styles.css, app.js) cùng origin
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.gemini_client import gemini_client
from app.routers import admin, auth, chat
from app.seed import seed_default_data
from app.vector_store import vector_store

_BOOTSTRAPPED = False


def bootstrap_system() -> None:
    """Khởi tạo schema SQLite và nạp dữ liệu mặc định (idempotent)."""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    init_db()
    seed_default_data()
    _BOOTSTRAPPED = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap_system()
    yield


app = FastAPI(
    title="LuậtAI — Hệ thống Hỏi đáp Pháp luật AI + RAG",
    description=(
        "Hệ thống truy vấn và giải đáp thắc mắc về pháp luật Việt Nam ứng dụng "
        "RAG (Retrieval-Augmented Generation), Local Embedding, ChromaDB, SQLite và Google Gemini API."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký các API routers
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(admin.router)


@app.get("/api/health", tags=["System"])
def health_check() -> dict[str, object]:
    """Kiểm tra trạng thái hoạt động của hệ thống, Local Embedding, Vector DB và Gemini API."""
    bootstrap_system()
    return {
        "status": "ok",
        "embedding_provider": settings.EMBEDDING_PROVIDER,
        "local_embedding_backend": gemini_client.localEngine.backend_name,
        "gemini_model": settings.GEMINI_MODEL,
        "gemini_api_key_configured": gemini_client._has_valid_api_key(),
        "vector_store_type": vector_store.type,
        "vector_count": vector_store.count(),
    }


# Mount giao diện tĩnh frontend/ ở cuối để không che các route /api/*
FRONTEND_DIR = settings.BASE_DIR / "frontend"

if FRONTEND_DIR.exists():
    @app.get("/", include_in_schema=False)
    def serve_index():
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    # Chạy trực tiếp 1 tiến trình ổn định trên Windows (không dùng reload để tránh treo SpawnProcess)
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)