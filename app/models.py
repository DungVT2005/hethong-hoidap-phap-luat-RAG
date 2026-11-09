"""
Mô hình hướng đối tượng (ORM Models) ánh xạ 8 bảng trong DB/legal_rag_schema_sqlite.sql
và hiện thực hóa các thuộc tính/phương thức trong Sơ đồ lớp (Class Diagram UML):
- User, Admin (kế thừa User)
- SourceDocument, DocumentChunk
- Question, Answer, AnswerSource
- ChatHistory, SystemConfig
"""
from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from app.database import Base, HAS_SQLALCHEMY


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _new_uuid() -> str:
    return str(uuid.uuid4())


def extract_article_heading(content: str, chunk_index: int | None = None) -> str:
    """Trích xuất tiêu đề Điều luật từ nội dung đoạn văn bản (ví dụ: 'Điều 113')."""
    if not content:
        return f"Đoạn #{chunk_index + 1}" if chunk_index is not None else "Trích đoạn"
    match = re.search(r"(Điều\s+\d+[a-zA-Z0-9]*)", content, flags=re.IGNORECASE)
    if match:
        article = match.group(1).strip()
        return article[0].upper() + article[1:]
    if chunk_index is not None:
        return f"Đoạn #{chunk_index + 1}"
    return "Trích đoạn"


if HAS_SQLALCHEMY:
    from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
    from sqlalchemy.orm import relationship

    class User(Base):
        __tablename__ = "users"

        user_id = Column(String, primary_key=True, default=_new_uuid)
        full_name = Column(String, nullable=False)
        email = Column(String, nullable=False, unique=True)
        password_hash = Column(String, nullable=False)
        role = Column(String, nullable=False, default="USER")
        status = Column(Integer, nullable=False, default=1)
        failed_login_attempts = Column(Integer, default=0)
        last_failed_login = Column(String, nullable=True)
        locked_until = Column(String, nullable=True)
        created_at = Column(String, nullable=False, default=_now_str)
        updated_at = Column(String, nullable=False, default=_now_str)

        documents = relationship("SourceDocument", back_populates="creator")
        questions = relationship(
            "Question", back_populates="user", cascade="all, delete-orphan"
        )
        histories = relationship(
            "ChatHistory", back_populates="user", cascade="all, delete-orphan"
        )

        # Các phương thức hướng đối tượng theo UML Class Diagram
        def login(self) -> bool:
            return bool(self.status == 1)

        def logout(self) -> bool:
            return True

        def changePassword(self, new_password_hash: str) -> None:
            self.password_hash = new_password_hash
            self.updated_at = _now_str()

        def updateProfile(self, full_name: str | None = None, email: str | None = None) -> None:
            if full_name:
                self.full_name = full_name
            if email:
                self.email = email
            self.updated_at = _now_str()

    class Admin(User):
        """Lớp Admin kế thừa từ User theo sơ đồ lớp UML."""

        __mapper_args__ = {"polymorphic_identity": "ADMIN", "concrete": False}

        def manageUser(self, target_user: User, new_status: bool) -> None:
            target_user.status = 1 if new_status else 0
            if new_status:
                target_user.failed_login_attempts = 0
                target_user.locked_until = None

        def manageSystem(self, config_key: str, config_value: str) -> dict[str, str]:
            return {"key": config_key, "value": config_value, "updated_by": self.user_id}

        def updateLegalData(self, document_title: str) -> str:
            return f"Admin {self.full_name} cập nhật tài liệu: {document_title}"

    class SourceDocument(Base):
        __tablename__ = "source_documents"

        document_id = Column(String, primary_key=True, default=_new_uuid)
        title = Column(String, nullable=False)
        document_type = Column(String, nullable=True)
        issue_date = Column(String, nullable=True)
        issuing_agency = Column(String, nullable=True)
        document_url = Column(String, nullable=True)
        content = Column(Text, nullable=True)
        file_name = Column(String, nullable=True)
        created_by = Column(
            String, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
        )
        created_at = Column(String, nullable=False, default=_now_str)
        updated_at = Column(String, nullable=False, default=_now_str)

        creator = relationship("User", back_populates="documents")
        chunks = relationship(
            "DocumentChunk",
            back_populates="document",
            cascade="all, delete-orphan",
            order_by="DocumentChunk.chunk_index",
        )
        answer_sources = relationship("AnswerSource", back_populates="document")

        def getRelevantChunks(self) -> list["DocumentChunk"]:
            return list(self.chunks or [])

        def getMetadata(self) -> dict[str, Any]:
            return {
                "document_id": self.document_id,
                "title": self.title,
                "document_type": self.document_type,
                "issue_date": self.issue_date,
                "issuing_agency": self.issuing_agency,
                "file_name": self.file_name,
            }

    class DocumentChunk(Base):
        __tablename__ = "document_chunks"

        chunk_id = Column(String, primary_key=True, default=_new_uuid)
        document_id = Column(
            String,
            ForeignKey("source_documents.document_id", ondelete="CASCADE"),
            nullable=False,
        )
        chunk_index = Column(Integer, nullable=False)
        content = Column(Text, nullable=False)
        token_count = Column(Integer, nullable=True)
        created_at = Column(String, nullable=False, default=_now_str)

        document = relationship("SourceDocument", back_populates="chunks")
        answer_sources = relationship("AnswerSource", back_populates="chunk")

        def getContent(self) -> str:
            return self.content

        def getArticleLabel(self) -> str:
            return extract_article_heading(self.content, self.chunk_index)

    class Question(Base):
        __tablename__ = "questions"

        question_id = Column(String, primary_key=True, default=_new_uuid)
        user_id = Column(
            String, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
        )
        content = Column(Text, nullable=False)
        status = Column(String, nullable=False, default="PENDING")
        created_at = Column(String, nullable=False, default=_now_str)

        user = relationship("User", back_populates="questions")
        answer = relationship(
            "Answer",
            back_populates="question",
            uselist=False,
            cascade="all, delete-orphan",
        )
        histories = relationship(
            "ChatHistory", back_populates="question", cascade="all, delete-orphan"
        )

        def process(self) -> None:
            self.status = "PROCESSING"

        def getAnswer(self) -> "Answer | None":
            return self.answer

    class Answer(Base):
        __tablename__ = "answers"

        answer_id = Column(String, primary_key=True, default=_new_uuid)
        question_id = Column(
            String,
            ForeignKey("questions.question_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        )
        content = Column(Text, nullable=False)
        model_name = Column(String, nullable=True)
        created_at = Column(String, nullable=False, default=_now_str)

        question = relationship("Question", back_populates="answer")
        sources = relationship(
            "AnswerSource",
            back_populates="answer",
            cascade="all, delete-orphan",
            order_by="AnswerSource.rank_no",
        )
        histories = relationship("ChatHistory", back_populates="answer")

        def getFormattedAnswer(self) -> str:
            return self.content

    class AnswerSource(Base):
        __tablename__ = "answer_sources"

        answer_id = Column(
            String,
            ForeignKey("answers.answer_id", ondelete="CASCADE"),
            primary_key=True,
        )
        document_id = Column(
            String,
            ForeignKey("source_documents.document_id", ondelete="RESTRICT"),
            primary_key=True,
        )
        chunk_id = Column(
            String,
            ForeignKey("document_chunks.chunk_id", ondelete="SET NULL"),
            primary_key=True,
        )
        rank_no = Column(Integer, nullable=True)
        score = Column(Float, nullable=True)

        answer = relationship("Answer", back_populates="sources")
        document = relationship("SourceDocument", back_populates="answer_sources")
        chunk = relationship("DocumentChunk", back_populates="answer_sources")

    class ChatHistory(Base):
        __tablename__ = "chat_histories"

        history_id = Column(String, primary_key=True, default=_new_uuid)
        user_id = Column(
            String, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
        )
        question_id = Column(
            String,
            ForeignKey("questions.question_id", ondelete="CASCADE"),
            nullable=False,
        )
        answer_id = Column(
            String, ForeignKey("answers.answer_id", ondelete="SET NULL"), nullable=True
        )
        created_at = Column(String, nullable=False, default=_now_str)

        user = relationship("User", back_populates="histories")
        question = relationship("Question", back_populates="histories")
        answer = relationship("Answer", back_populates="histories")

    class SystemConfig(Base):
        __tablename__ = "system_config"

        config_key = Column(String, primary_key=True)
        config_value = Column(Text, nullable=False)
        updated_by = Column(
            String, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
        )
        updated_at = Column(String, nullable=False, default=_now_str)

else:
    # =========================================================================
    # Các lớp Model tương thích hoàn toàn khi chạy trên môi trường chỉ có sqlite3
    # =========================================================================
    class User(Base):
        __tablename__ = "users"

        def __init__(
            self,
            user_id: str | None = None,
            full_name: str = "",
            email: str = "",
            password_hash: str = "",
            role: str = "USER",
            status: int = 1,
            failed_login_attempts: int = 0,
            last_failed_login: str | None = None,
            locked_until: str | None = None,
            created_at: str | None = None,
            updated_at: str | None = None,
        ) -> None:
            self.user_id = user_id or _new_uuid()
            self.full_name = full_name
            self.email = email
            self.password_hash = password_hash
            self.role = role
            self.status = int(status)
            self.failed_login_attempts = int(failed_login_attempts or 0)
            self.last_failed_login = last_failed_login
            self.locked_until = locked_until
            self.created_at = created_at or _now_str()
            self.updated_at = updated_at or _now_str()

        def login(self) -> bool:
            return bool(self.status == 1)

        def logout(self) -> bool:
            return True

        def changePassword(self, new_password_hash: str) -> None:
            self.password_hash = new_password_hash
            self.updated_at = _now_str()

        def updateProfile(self, full_name: str | None = None, email: str | None = None) -> None:
            if full_name:
                self.full_name = full_name
            if email:
                self.email = email
            self.updated_at = _now_str()

        def _sync_to_sqlite(self, conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT INTO users (
                    user_id, full_name, email, password_hash, role, status,
                    failed_login_attempts, last_failed_login, locked_until, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    full_name = excluded.full_name,
                    email = excluded.email,
                    password_hash = excluded.password_hash,
                    role = excluded.role,
                    status = excluded.status,
                    failed_login_attempts = excluded.failed_login_attempts,
                    last_failed_login = excluded.last_failed_login,
                    locked_until = excluded.locked_until,
                    updated_at = excluded.updated_at
                """,
                (
                    self.user_id,
                    self.full_name,
                    self.email,
                    self.password_hash,
                    self.role,
                    self.status,
                    self.failed_login_attempts,
                    self.last_failed_login,
                    self.locked_until,
                    self.created_at,
                    self.updated_at,
                ),
            )

    class Admin(User):
        def manageUser(self, target_user: User, new_status: bool) -> None:
            target_user.status = 1 if new_status else 0
            if new_status:
                target_user.failed_login_attempts = 0
                target_user.locked_until = None

    class SourceDocument(Base):
        __tablename__ = "source_documents"

        def __init__(
            self,
            document_id: str | None = None,
            title: str = "",
            document_type: str | None = None,
            issue_date: str | None = None,
            issuing_agency: str | None = None,
            document_url: str | None = None,
            content: str | None = None,
            file_name: str | None = None,
            created_by: str | None = None,
            created_at: str | None = None,
            updated_at: str | None = None,
        ) -> None:
            self.document_id = document_id or _new_uuid()
            self.title = title
            self.document_type = document_type
            self.issue_date = issue_date
            self.issuing_agency = issuing_agency
            self.document_url = document_url
            self.content = content
            self.file_name = file_name
            self.created_by = created_by
            self.created_at = created_at or _now_str()
            self.updated_at = updated_at or _now_str()
            self.chunks: list[DocumentChunk] = []

        def getRelevantChunks(self) -> list["DocumentChunk"]:
            return list(self.chunks or [])

        def getMetadata(self) -> dict[str, Any]:
            return {
                "document_id": self.document_id,
                "title": self.title,
                "document_type": self.document_type,
                "issue_date": self.issue_date,
                "issuing_agency": self.issuing_agency,
                "file_name": self.file_name,
            }

        def _sync_to_sqlite(self, conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT INTO source_documents (
                    document_id, title, document_type, issue_date, issuing_agency,
                    document_url, content, file_name, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    title = excluded.title,
                    document_type = excluded.document_type,
                    issue_date = excluded.issue_date,
                    issuing_agency = excluded.issuing_agency,
                    document_url = excluded.document_url,
                    content = excluded.content,
                    file_name = excluded.file_name,
                    updated_at = excluded.updated_at
                """,
                (
                    self.document_id,
                    self.title,
                    self.document_type,
                    self.issue_date,
                    self.issuing_agency,
                    self.document_url,
                    self.content,
                    self.file_name,
                    self.created_by,
                    self.created_at,
                    self.updated_at,
                ),
            )

    class DocumentChunk(Base):
        __tablename__ = "document_chunks"

        def __init__(
            self,
            chunk_id: str | None = None,
            document_id: str = "",
            chunk_index: int = 0,
            content: str = "",
            token_count: int | None = None,
            created_at: str | None = None,
        ) -> None:
            self.chunk_id = chunk_id or _new_uuid()
            self.document_id = document_id
            self.chunk_index = int(chunk_index)
            self.content = content
            self.token_count = token_count
            self.created_at = created_at or _now_str()
            self.document: SourceDocument | None = None

        def getContent(self) -> str:
            return self.content

        def getArticleLabel(self) -> str:
            return extract_article_heading(self.content, self.chunk_index)

        def _sync_to_sqlite(self, conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT INTO document_chunks (
                    chunk_id, document_id, chunk_index, content, token_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    content = excluded.content,
                    token_count = excluded.token_count
                """,
                (
                    self.chunk_id,
                    self.document_id,
                    self.chunk_index,
                    self.content,
                    self.token_count,
                    self.created_at,
                ),
            )

    class Question(Base):
        __tablename__ = "questions"

        def __init__(
            self,
            question_id: str | None = None,
            user_id: str = "",
            content: str = "",
            status: str = "PENDING",
            created_at: str | None = None,
        ) -> None:
            self.question_id = question_id or _new_uuid()
            self.user_id = user_id
            self.content = content
            self.status = status
            self.created_at = created_at or _now_str()
            self.answer: Answer | None = None

        def process(self) -> None:
            self.status = "PROCESSING"

        def _sync_to_sqlite(self, conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT INTO questions (question_id, user_id, content, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(question_id) DO UPDATE SET
                    content = excluded.content,
                    status = excluded.status
                """,
                (self.question_id, self.user_id, self.content, self.status, self.created_at),
            )

    class Answer(Base):
        __tablename__ = "answers"

        def __init__(
            self,
            answer_id: str | None = None,
            question_id: str = "",
            content: str = "",
            model_name: str | None = None,
            created_at: str | None = None,
        ) -> None:
            self.answer_id = answer_id or _new_uuid()
            self.question_id = question_id
            self.content = content
            self.model_name = model_name
            self.created_at = created_at or _now_str()
            self.sources: list[AnswerSource] = []

        def getFormattedAnswer(self) -> str:
            return self.content

        def _sync_to_sqlite(self, conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT INTO answers (answer_id, question_id, content, model_name, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(answer_id) DO UPDATE SET
                    content = excluded.content,
                    model_name = excluded.model_name
                """,
                (self.answer_id, self.question_id, self.content, self.model_name, self.created_at),
            )

    class AnswerSource(Base):
        __tablename__ = "answer_sources"

        def __init__(
            self,
            answer_id: str = "",
            document_id: str = "",
            chunk_id: str | None = None,
            rank_no: int | None = None,
            score: float | None = None,
        ) -> None:
            self.answer_id = answer_id
            self.document_id = document_id
            self.chunk_id = chunk_id
            self.rank_no = rank_no
            self.score = score
            self.document: SourceDocument | None = None
            self.chunk: DocumentChunk | None = None

        def _sync_to_sqlite(self, conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT OR REPLACE INTO answer_sources (
                    answer_id, document_id, chunk_id, rank_no, score
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (self.answer_id, self.document_id, self.chunk_id, self.rank_no, self.score),
            )

    class ChatHistory(Base):
        __tablename__ = "chat_histories"

        def __init__(
            self,
            history_id: str | None = None,
            user_id: str = "",
            question_id: str = "",
            answer_id: str | None = None,
            created_at: str | None = None,
        ) -> None:
            self.history_id = history_id or _new_uuid()
            self.user_id = user_id
            self.question_id = question_id
            self.answer_id = answer_id
            self.created_at = created_at or _now_str()
            self.question: Question | None = None
            self.answer: Answer | None = None

        def _sync_to_sqlite(self, conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT OR REPLACE INTO chat_histories (
                    history_id, user_id, question_id, answer_id, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (self.history_id, self.user_id, self.question_id, self.answer_id, self.created_at),
            )

    class SystemConfig(Base):
        __tablename__ = "system_config"

        def __init__(
            self,
            config_key: str = "",
            config_value: str = "",
            updated_by: str | None = None,
            updated_at: str | None = None,
        ) -> None:
            self.config_key = config_key
            self.config_value = config_value
            self.updated_by = updated_by
            self.updated_at = updated_at or _now_str()

        def _sync_to_sqlite(self, conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT INTO system_config (config_key, config_value, updated_by, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(config_key) DO UPDATE SET
                    config_value = excluded.config_value,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """,
                (self.config_key, self.config_value, self.updated_by, self.updated_at),
            )
