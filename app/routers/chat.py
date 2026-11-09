"""
Router Hỏi đáp Pháp luật & Lịch sử Hội thoại (/api/questions, /api/history):
- POST /api/questions : Đặt câu hỏi pháp luật (RAG + Gemini API)
- GET  /api/history   : Lấy danh sách lịch sử hỏi đáp kèm nguồn trích dẫn của người dùng
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import HAS_SQLALCHEMY, get_db
from app.dependencies import get_current_user
from app.mappers import map_conversation_to_dict, map_source_to_dict
from app.models import (
    Answer,
    AnswerSource,
    ChatHistory,
    DocumentChunk,
    Question,
    SourceDocument,
    User,
)
from app.rag_service import rag_service
from app.schemas import ConversationResponse, QuestionRequest

router = APIRouter(prefix="/api", tags=["Chat & Legal RAG"])


@router.post("/questions", response_model=ConversationResponse)
def ask_question(
    payload: QuestionRequest,
    current_user: User = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> dict[str, Any]:
    """
    Nhận câu hỏi pháp luật từ người dùng, thực thi pipeline RAG:
    Local Embedding -> ChromaDB Top-5 Cosine Search -> Gemini Answer Generation -> Lưu CSDL.
    """
    try:
        return rag_service.answerQuestion(
            db=db,
            user_id=current_user.user_id,
            question_content=payload.content,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi xử lý câu hỏi: {exc}",
        ) from exc


@router.get("/history", response_model=list[ConversationResponse])
def get_chat_history(
    current_user: User = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> list[dict[str, Any]]:
    """Lấy danh sách lịch sử hội thoại của người dùng hiện tại kèm trích dẫn nguồn."""
    conversations: list[dict[str, Any]] = []

    if HAS_SQLALCHEMY:
        histories = (
            db.query(ChatHistory)
            .filter(ChatHistory.user_id == current_user.user_id)
            .order_by(ChatHistory.created_at.desc())
            .all()
        )
        for h in histories:
            q = h.question
            a = h.answer
            if not q or not a:
                continue

            sources_list: list[dict[str, Any]] = []
            for src in a.sources or []:
                doc_title = src.document.title if src.document else "Văn bản pháp luật"
                chunk_content = src.chunk.content if src.chunk else ""
                chunk_idx = src.chunk.chunk_index if src.chunk else None
                sources_list.append(
                    map_source_to_dict(
                        document_id=src.document_id,
                        title=doc_title,
                        chunk_id=src.chunk_id,
                        chunk_content=chunk_content,
                        chunk_index=chunk_idx,
                        score=src.score,
                        rank_no=src.rank_no,
                    )
                )

            conversations.append(
                map_conversation_to_dict(
                    history_id=h.history_id,
                    question=q,
                    answer=a,
                    sources=sources_list,
                )
            )
        return conversations

    # Truy vấn trên FallbackSQLiteSession
    history_rows = db.fetchall_dicts(
        """
        SELECT h.history_id, h.created_at AS history_created_at,
               q.question_id, q.content AS q_content, q.status AS q_status, q.created_at AS q_created_at,
               a.answer_id, a.content AS a_content, a.model_name, a.created_at AS a_created_at
          FROM chat_histories h
          JOIN questions q ON q.question_id = h.question_id
          JOIN answers a ON a.answer_id = h.answer_id
         WHERE h.user_id = ?
         ORDER BY h.created_at DESC, h.rowid DESC
        """,
        (current_user.user_id,),
    )

    for row in history_rows:
        src_rows = db.fetchall_dicts(
            """
            SELECT s.document_id, s.chunk_id, s.rank_no, s.score,
                   d.title AS doc_title,
                   c.content AS chunk_content, c.chunk_index
              FROM answer_sources s
              JOIN source_documents d ON d.document_id = s.document_id
              LEFT JOIN document_chunks c ON c.chunk_id = s.chunk_id
             WHERE s.answer_id = ?
             ORDER BY s.rank_no ASC
            """,
            (row["answer_id"],),
        )
        sources_list = [
            map_source_to_dict(
                document_id=s["document_id"],
                title=s.get("doc_title") or "Văn bản pháp luật",
                chunk_id=s.get("chunk_id"),
                chunk_content=s.get("chunk_content") or "",
                chunk_index=s.get("chunk_index"),
                score=s.get("score"),
                rank_no=s.get("rank_no"),
            )
            for s in src_rows
        ]
        conversations.append(
            map_conversation_to_dict(
                history_id=row["history_id"],
                question={
                    "question_id": row["question_id"],
                    "content": row["q_content"],
                    "status": row["q_status"],
                    "created_at": row["q_created_at"],
                },
                answer={
                    "answer_id": row["answer_id"],
                    "content": row["a_content"],
                    "model_name": row["model_name"],
                    "created_at": row["a_created_at"],
                },
                sources=sources_list,
            )
        )

    return conversations
