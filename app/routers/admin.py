"""
Router Quản trị Hệ thống (/api/admin/*):
- GET    /api/admin/users                : Danh sách toàn bộ người dùng
- PATCH  /api/admin/users/{user_id}/status : Khóa / Mở khóa tài khoản người dùng
- GET    /api/admin/documents            : Danh sách văn bản pháp luật kèm số lượng chunks
- POST   /api/admin/documents            : Upload file văn bản luật (.pdf, .docx, .txt, .md) và nạp vào RAG
- DELETE /api/admin/documents/{doc_id}   : Xóa văn bản luật khỏi SQLite và ChromaDB
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.database import HAS_SQLALCHEMY, get_db
from app.dependencies import find_user_by_id, require_admin
from app.mappers import map_document_to_dict, map_user_to_dict
from app.models import Admin, DocumentChunk, SourceDocument, User
from app.rag_service import rag_service
from app.schemas import (
    DocumentResponse,
    UpdateUserStatusRequest,
    UploadDocumentResponse,
    UserResponse,
)

router = APIRouter(prefix="/api/admin", tags=["Administration"])


@router.get("/users", response_model=list[UserResponse])
def list_users(
    current_admin: User = Depends(require_admin),
    db: Any = Depends(get_db),
) -> list[dict[str, Any]]:
    """Lấy danh sách tất cả người dùng trong hệ thống (chỉ dành cho ADMIN)."""
    if HAS_SQLALCHEMY:
        users = db.query(User).order_by(User.created_at.desc()).all()
        return [map_user_to_dict(u) for u in users]

    rows = db.fetchall_dicts("SELECT * FROM users ORDER BY created_at DESC, rowid DESC")
    return [map_user_to_dict(r) for r in rows]


@router.patch("/users/{user_id}/status", response_model=UserResponse)
def update_user_status(
    user_id: str,
    payload: UpdateUserStatusRequest,
    current_admin: User = Depends(require_admin),
    db: Any = Depends(get_db),
) -> dict[str, Any]:
    """Khóa hoặc mở khóa tài khoản người dùng."""
    if user_id == current_admin.user_id and not payload.status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể tự khóa tài khoản Quản trị viên đang đăng nhập.",
        )

    target_user = find_user_by_id(db, user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy người dùng.",
        )

    # Sử dụng phương thức hướng đối tượng từ lớp Admin
    admin_actor = Admin(
        user_id=current_admin.user_id,
        full_name=current_admin.full_name,
        email=current_admin.email,
        password_hash=current_admin.password_hash,
        role="ADMIN",
        status=current_admin.status,
    )
    admin_actor.manageUser(target_user, payload.status)

    db.add(target_user)
    db.commit()
    return map_user_to_dict(target_user)


@router.get("/documents", response_model=list[DocumentResponse])
def list_documents(
    current_admin: User = Depends(require_admin),
    db: Any = Depends(get_db),
) -> list[dict[str, Any]]:
    """Lấy danh sách tất cả các văn bản pháp luật kèm tổng số đoạn (chunks) đã chia."""
    if HAS_SQLALCHEMY:
        docs = (
            db.query(SourceDocument)
            .order_by(SourceDocument.created_at.desc())
            .all()
        )
        results: list[dict[str, Any]] = []
        for d in docs:
            cnt = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == d.document_id)
                .count()
            )
            results.append(map_document_to_dict(d, chunk_count=cnt))
        return results

    rows = db.fetchall_dicts(
        """
        SELECT d.*,
               (SELECT COUNT(*) FROM document_chunks c WHERE c.document_id = d.document_id) AS chunk_count
          FROM source_documents d
         ORDER BY d.created_at DESC, d.rowid DESC
        """
    )
    return [map_document_to_dict(r) for r in rows]


@router.post(
    "/documents",
    response_model=UploadDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(default=""),
    type: str = Form(default="Văn bản"),
    agency: str = Form(default=""),
    issueDate: str = Form(default=""),
    current_admin: User = Depends(require_admin),
    db: Any = Depends(get_db),
) -> dict[str, Any]:
    """
    Nhận file văn bản (.txt, .md, .pdf, .docx) từ Quản trị viên,
    chạy pipeline RAG (trích xuất -> chia Điều -> tạo Local Embedding -> lưu SQLite & ChromaDB).
    """
    filename = file.filename or "van_ban_phap_luat.txt"
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File tải lên rỗng. Vui lòng chọn một file hợp lệ.",
        )

    try:
        doc_dict = rag_service.ingestDocument(
            db=db,
            filename=filename,
            file_bytes=file_bytes,
            title=title.strip() or filename,
            document_type=type.strip() or "Văn bản",
            issuing_agency=agency.strip(),
            issue_date=issueDate.strip(),
            created_by=current_admin.user_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return {
        "message": (
            f"Đã tải lên và nạp thành công '{doc_dict['title']}' "
            f"({doc_dict['chunks']} đoạn/Điều) vào SQLite & ChromaDB."
        ),
        "document": doc_dict,
    }


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: str,
    current_admin: User = Depends(require_admin),
    db: Any = Depends(get_db),
) -> dict[str, str]:
    """Xóa một văn bản pháp luật khỏi SQLite và ChromaDB."""
    try:
        rag_service.vectorDB.delete(document_id=document_id)
        if HAS_SQLALCHEMY:
            doc = (
                db.query(SourceDocument)
                .filter(SourceDocument.document_id == document_id)
                .first()
            )
            if not doc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Không tìm thấy văn bản pháp luật.",
                )
            db.delete(doc)
            db.commit()
        else:
            row = db.fetchone_dict(
                "SELECT document_id FROM source_documents WHERE document_id = ?",
                (document_id,),
            )
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Không tìm thấy văn bản pháp luật.",
                )
            db.execute_sql(
                "DELETE FROM source_documents WHERE document_id = ?", (document_id,)
            )
            db.commit()
        return {"message": "Đã xóa văn bản pháp luật khỏi hệ thống."}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Không thể xóa văn bản (có thể đang được tham chiếu bởi câu trả lời): {exc}",
        ) from exc
