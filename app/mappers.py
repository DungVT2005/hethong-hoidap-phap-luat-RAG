"""
Chuyển đổi các đối tượng Model CSDL (ORM / SQLite rows) sang cấu trúc JSON
mà giao diện frontend/app.js yêu cầu.
"""
from __future__ import annotations

from typing import Any
from app.models import (
    Answer,
    DocumentChunk,
    Question,
    SourceDocument,
    User,
    extract_article_heading,
)


def map_user_to_dict(user: User | dict[str, Any]) -> dict[str, Any]:
    """Chuyển User model sang dict cho frontend (id, name, email, role, status, createdAt)."""
    if isinstance(user, dict):
        return {
            "id": user["user_id"],
            "name": user["full_name"],
            "email": user["email"],
            "role": user["role"],
            "status": bool(int(user.get("status", 1))),
            "createdAt": user.get("created_at") or "",
        }
    return {
        "id": user.user_id,
        "name": user.full_name,
        "email": user.email,
        "role": user.role,
        "status": bool(int(user.status)),
        "createdAt": user.created_at or "",
    }


def map_document_to_dict(
    doc: SourceDocument | dict[str, Any], chunk_count: int | None = None
) -> dict[str, Any]:
    """Chuyển SourceDocument sang dict cho bảng Quản lý văn bản của Admin."""
    if isinstance(doc, dict):
        chunks_num = (
            chunk_count
            if chunk_count is not None
            else int(doc.get("chunk_count", 0) or 0)
        )
        return {
            "id": doc["document_id"],
            "title": doc["title"],
            "type": doc.get("document_type") or "Văn bản",
            "agency": doc.get("issuing_agency") or "—",
            "issueDate": doc.get("issue_date") or "—",
            "chunks": chunks_num,
            "fileName": doc.get("file_name") or "",
            "createdAt": doc.get("created_at") or "",
        }

    chunks_num = (
        chunk_count
        if chunk_count is not None
        else (len(doc.chunks) if hasattr(doc, "chunks") and doc.chunks is not None else 0)
    )
    return {
        "id": doc.document_id,
        "title": doc.title,
        "type": doc.document_type or "Văn bản",
        "agency": doc.issuing_agency or "—",
        "issueDate": doc.issue_date or "—",
        "chunks": chunks_num,
        "fileName": doc.file_name or "",
        "createdAt": doc.created_at or "",
    }


def map_source_to_dict(
    document_id: str,
    title: str,
    chunk_id: str | None,
    chunk_content: str,
    chunk_index: int | None,
    score: float | None,
    rank_no: int | None,
) -> dict[str, Any]:
    """
    Chuyển thông tin trích dẫn nguồn sang định dạng chip & modal của frontend:
    { documentId, chunkId, title, article, excerpt, score, rank }
    """
    article = extract_article_heading(chunk_content, chunk_index)
    excerpt = (chunk_content or "").strip()
    return {
        "documentId": document_id,
        "chunkId": chunk_id,
        "title": title,
        "article": article,
        "excerpt": excerpt,
        "score": round(float(score or 0.0), 4),
        "rank": int(rank_no or 1),
    }


def map_conversation_to_dict(
    history_id: str,
    question: Question | dict[str, Any],
    answer: Answer | dict[str, Any],
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Chuyển cặp Question - Answer kèm danh sách nguồn sang ConversationResponse."""
    if isinstance(question, dict):
        q_dict = {
            "id": question["question_id"],
            "content": question["content"],
            "status": question.get("status", "COMPLETED"),
            "createdAt": question.get("created_at") or "",
        }
    else:
        q_dict = {
            "id": question.question_id,
            "content": question.content,
            "status": question.status,
            "createdAt": question.created_at or "",
        }

    if isinstance(answer, dict):
        a_dict = {
            "id": answer["answer_id"],
            "content": answer["content"],
            "model": answer.get("model_name") or "gemini-2.5-flash",
            "createdAt": answer.get("created_at") or "",
            "sources": sources,
        }
    else:
        a_dict = {
            "id": answer.answer_id,
            "content": answer.content,
            "model": answer.model_name or "gemini-2.5-flash",
            "createdAt": answer.created_at or "",
            "sources": sources,
        }

    return {
        "id": history_id,
        "question": q_dict,
        "answer": a_dict,
    }
