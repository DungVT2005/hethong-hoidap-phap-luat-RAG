"""
Khởi tạo dữ liệu mặc định (Seed Data) & Tự động chuẩn hóa lại các đoạn văn bản (Chunks)
nếu phát hiện dữ liệu PDF cũ trong SQLite bị ngắt dòng, gộp Phụ lục vào Điều cuối,
hoặc tách nhầm "Điều N của Luật này".
"""
from __future__ import annotations

import uuid

from app.auth_utils import hash_password
from app.config import settings
from app.database import HAS_SQLALCHEMY, open_session
from app.dependencies import find_user_by_identifier
from app.document_processor import (
    clean_legal_text,
    estimate_token_count,
    split_legal_text_by_article,
)
from app.models import (
    AnswerSource,
    DocumentChunk,
    SourceDocument,
    SystemConfig,
    User,
    extract_article_heading,
)
from app.rag_service import rag_service

CHUNK_SCHEMA_VERSION = "v4_focused_clause_rag"

SAMPLE_DOCUMENTS_META = [
    {
        "filename": "bo_luat_lao_dong_2019.txt",
        "title": "Bộ luật Lao động số 45/2019/QH14",
        "type": "Bộ luật",
        "agency": "Quốc hội",
        "issue_date": "2019-11-20",
    },
    {
        "filename": "bo_luat_dan_su_2015_thua_ke.txt",
        "title": "Bộ luật Dân sự số 91/2015/QH13 (Chế định Thừa kế)",
        "type": "Bộ luật",
        "agency": "Quốc hội",
        "issue_date": "2015-11-24",
    },
    {
        "filename": "luat_giao_thong_nghi_dinh_168.txt",
        "title": "Luật TTATGT đường bộ 2024 & Nghị định 168/2024/NĐ-CP",
        "type": "Nghị định",
        "agency": "Chính phủ",
        "issue_date": "2024-12-26",
    },
]


def _rebuild_all_document_chunks_and_vectors(db) -> int:
   
    total_chunks = 0
    if HAS_SQLALCHEMY:
        docs = db.query(SourceDocument).all()
        if not docs:
            return 0
        for doc in docs:
            if not doc.content:
                continue
            rag_service.vectorDB.delete(document_id=doc.document_id)
            db.query(AnswerSource).filter(
                AnswerSource.document_id == doc.document_id
            ).delete()
            db.query(DocumentChunk).filter(
                DocumentChunk.document_id == doc.document_id
            ).delete()
            db.flush()

            cleaned = clean_legal_text(doc.content)
            doc.content = cleaned
            chunk_texts = split_legal_text_by_article(cleaned)
            if not chunk_texts:
                continue
            embeddings = rag_service.aiService.embed_documents(chunk_texts)
            cids: list[str] = []
            metas: list[dict] = []
            for idx, c_text in enumerate(chunk_texts):
                cid = str(uuid.uuid4())
                cids.append(cid)
                db.add(
                    DocumentChunk(
                        chunk_id=cid,
                        document_id=doc.document_id,
                        chunk_index=idx,
                        content=c_text,
                        token_count=estimate_token_count(c_text),
                    )
                )
                metas.append(
                    {
                        "document_id": doc.document_id,
                        "chunk_index": idx,
                        "title": doc.title,
                        "document_type": doc.document_type or "Văn bản",
                        "article": extract_article_heading(c_text, idx),
                    }
                )
            db.flush()
            rag_service.vectorDB.storeEmbedding(
                ids=cids,
                embeddings=embeddings,
                documents=chunk_texts,
                metadatas=metas,
            )
            total_chunks += len(cids)
        db.commit()
    else:
        doc_rows = db.fetchall_dicts("SELECT * FROM source_documents")
        if not doc_rows:
            return 0
        for d in doc_rows:
            raw_content = d.get("content") or ""
            if not raw_content:
                continue
            doc_id = d["document_id"]
            rag_service.vectorDB.delete(document_id=doc_id)
            db.execute_sql(
                "DELETE FROM answer_sources WHERE document_id = ?", (doc_id,)
            )
            db.execute_sql(
                "DELETE FROM document_chunks WHERE document_id = ?", (doc_id,)
            )
            cleaned = clean_legal_text(raw_content)
            db.execute_sql(
                "UPDATE source_documents SET content = ? WHERE document_id = ?",
                (cleaned, doc_id),
            )
            chunk_texts = split_legal_text_by_article(cleaned)
            if not chunk_texts:
                continue
            embeddings = rag_service.aiService.embed_documents(chunk_texts)
            cids = []
            metas = []
            for idx, c_text in enumerate(chunk_texts):
                cid = str(uuid.uuid4())
                cids.append(cid)
                db.add(
                    DocumentChunk(
                        chunk_id=cid,
                        document_id=doc_id,
                        chunk_index=idx,
                        content=c_text,
                        token_count=estimate_token_count(c_text),
                    )
                )
                metas.append(
                    {
                        "document_id": doc_id,
                        "chunk_index": idx,
                        "title": d["title"],
                        "document_type": d.get("document_type") or "Văn bản",
                        "article": extract_article_heading(c_text, idx),
                    }
                )
            db.flush()
            rag_service.vectorDB.storeEmbedding(
                ids=cids,
                embeddings=embeddings,
                documents=chunk_texts,
                metadatas=metas,
            )
            total_chunks += len(cids)
        db.commit()
    return total_chunks


def seed_default_data() -> None:
    """Tạo tài khoản admin/user mặc định, cấu hình hệ thống và nạp/chuẩn hóa văn bản luật."""
    db = open_session()
    try:
        admin_user = find_user_by_identifier(db, settings.SEED_ADMIN_EMAIL)
        if not admin_user:
            admin_user = User(
                user_id="u_admin_001",
                full_name=settings.SEED_ADMIN_NAME,
                email=settings.SEED_ADMIN_EMAIL,
                password_hash=hash_password(settings.SEED_ADMIN_PASSWORD),
                role="ADMIN",
                status=1,
            )
            db.add(admin_user)
            db.commit()

        normal_user = find_user_by_identifier(db, settings.SEED_USER_EMAIL)
        if not normal_user:
            normal_user = User(
                user_id="u_user_001",
                full_name=settings.SEED_USER_NAME,
                email=settings.SEED_USER_EMAIL,
                password_hash=hash_password(settings.SEED_USER_PASSWORD),
                role="USER",
                status=1,
            )
            db.add(normal_user)
            db.commit()

        # Kiểm tra phiên bản thuật toán chia đoạn (chunk_schema_version)
        current_version = None
        if HAS_SQLALCHEMY:
            ver_cfg = (
                db.query(SystemConfig)
                .filter(SystemConfig.config_key == "chunk_schema_version")
                .first()
            )
            if ver_cfg:
                current_version = ver_cfg.config_value
        else:
            ver_row = db.fetchone_dict(
                "SELECT config_value FROM system_config WHERE config_key = 'chunk_schema_version'"
            )
            if ver_row:
                current_version = ver_row["config_value"]

        default_configs = {
            "embedding_provider": settings.EMBEDDING_PROVIDER,
            "local_embedding_model": settings.LOCAL_EMBEDDING_MODEL,
            "gemini_model": settings.GEMINI_MODEL,
            "rag_top_k": str(settings.RAG_TOP_K),
            "chunk_max_chars": str(settings.CHUNK_MAX_CHARS),
            "chunk_overlap_chars": str(settings.CHUNK_OVERLAP_CHARS),
            "chunk_schema_version": CHUNK_SCHEMA_VERSION,
        }
        for k, v in default_configs.items():
            if HAS_SQLALCHEMY:
                existing = (
                    db.query(SystemConfig)
                    .filter(SystemConfig.config_key == k)
                    .first()
                )
                if not existing:
                    db.add(
                        SystemConfig(
                            config_key=k,
                            config_value=v,
                            updated_by=admin_user.user_id,
                        )
                    )
                elif k == "chunk_schema_version":
                    existing.config_value = v
            else:
                db.add(
                    SystemConfig(
                        config_key=k,
                        config_value=v,
                        updated_by=admin_user.user_id,
                    )
                )
        db.commit()

        if settings.SEED_SAMPLE_DOCS:
            if HAS_SQLALCHEMY:
                doc_count = db.query(SourceDocument).count()
            else:
                cnt_row = db.fetchone_dict(
                    "SELECT COUNT(*) AS cnt FROM source_documents"
                )
                doc_count = int(cnt_row["cnt"]) if cnt_row else 0

            if doc_count == 0:
                sample_dir = settings.BASE_DIR / "sample_docs"
                for meta in SAMPLE_DOCUMENTS_META:
                    fpath = sample_dir / meta["filename"]
                    if fpath.exists():
                        rag_service.ingestDocument(
                            db=db,
                            filename=meta["filename"],
                            file_bytes=fpath.read_bytes(),
                            title=meta["title"],
                            document_type=meta["type"],
                            issuing_agency=meta["agency"],
                            issue_date=meta["issue_date"],
                            created_by=admin_user.user_id,
                        )
            elif (
                current_version != CHUNK_SCHEMA_VERSION
                or rag_service.vectorDB.count() == 0
            ):
                _rebuild_all_document_chunks_and_vectors(db)
    finally:
        db.close()