"""
Kết nối CSDL SQLite, khởi tạo bảng/trigger/index từ file legal_rag_schema_sqlite.sql,
bật khóa ngoại (PRAGMA foreign_keys = ON) và cung cấp phiên làm việc ORM.
Hỗ trợ 100% cho Windows (NTFS), macOS, Linux và môi trường ảo hóa.
"""
from __future__ import annotations

import os
import sqlite3
from typing import Any, Generator

from app.config import settings

# Kiểm tra SQLAlchemy ORM
try:
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import Session, declarative_base, sessionmaker

    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False
    Session = Any  # type: ignore

# Đảm bảo thư mục chứa DB tồn tại
settings.SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{settings.SQLITE_DB_PATH.as_posix()}"


def _open_raw_sqlite() -> sqlite3.Connection:
    """
    Mở kết nối SQLite chuẩn, bật khóa ngoại (PRAGMA foreign_keys = ON)
    và tương thích hoàn toàn trên Windows (Antigravity / VS Code), macOS, Linux.
    """
    settings.SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db_path_str = str(settings.SQLITE_DB_PATH)

    if os.name == "nt":
        # Trên Windows: kết nối trực tiếp đường dẫn chuẩn của Windows
        conn = sqlite3.connect(db_path_str, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row
        return conn

    # Trên Linux / macOS / Container
    try:
        posix_path = settings.SQLITE_DB_PATH.as_posix()
        conn = sqlite3.connect(
            f"file:{posix_path}?nolock=1", uri=True, check_same_thread=False
        )
        conn.execute("PRAGMA journal_mode = MEMORY;")
        conn.execute("PRAGMA synchronous = OFF;")
        conn.execute("PRAGMA temp_store = MEMORY;")
        conn.execute("PRAGMA foreign_keys = ON;")
    except sqlite3.OperationalError:
        conn = sqlite3.connect(db_path_str, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON;")

    conn.row_factory = sqlite3.Row
    return conn


class Database:
    """
    Lớp Database theo sơ đồ lớp UML:
    - dbType: String
    - connectionString: String
    + connect()
    + executeQuery()
    + close()
    """

    def __init__(
        self, db_type: str = "SQLite", connection_string: str = DATABASE_URL
    ) -> None:
        self.dbType = db_type
        self.connectionString = connection_string
        self._raw_conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        self._raw_conn = _open_raw_sqlite()
        return self._raw_conn

    def executeQuery(
        self, query: str, params: tuple | dict = ()
    ) -> list[dict[str, Any]]:
        conn = self._raw_conn or self.connect()
        cur = conn.execute(query, params)
        if query.strip().upper().startswith("SELECT"):
            return [dict(r) for r in cur.fetchall()]
        conn.commit()
        return []

    def close(self) -> None:
        if self._raw_conn is not None:
            self._raw_conn.close()
            self._raw_conn = None


if HAS_SQLALCHEMY:
    engine = create_engine(
        DATABASE_URL,
        creator=_open_raw_sqlite,
        connect_args={"check_same_thread": False},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.close()

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
else:
    engine = None

    class _FallbackBase:
        pass

    Base = _FallbackBase


class FallbackSQLiteSession:
    """
    Phiên làm việc SQLite dự phòng (khi môi trường chạy chưa cài gói SQLAlchemy),
    hỗ trợ đầy đủ giao dịch (commit / rollback / close) và bật PRAGMA foreign_keys = ON.
    """

    def __init__(self) -> None:
        self.conn = _open_raw_sqlite()
        self._pending_objects: list[Any] = []

    def execute_sql(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def fetchall_dicts(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        cur = self.conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    def fetchone_dict(
        self, sql: str, params: tuple | list = ()
    ) -> dict[str, Any] | None:
        cur = self.conn.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None

    def add(self, obj: Any) -> None:
        self._pending_objects.append(obj)

    def flush(self) -> None:
        for obj in self._pending_objects:
            if hasattr(obj, "_sync_to_sqlite"):
                obj._sync_to_sqlite(self.conn)
        self._pending_objects.clear()

    def commit(self) -> None:
        self.flush()
        self.conn.commit()

    def rollback(self) -> None:
        self._pending_objects.clear()
        self.conn.rollback()

    def refresh(self, obj: Any) -> None:
        if hasattr(obj, "_refresh_from_sqlite"):
            obj._refresh_from_sqlite(self.conn)

    def delete(self, obj: Any) -> None:
        if hasattr(obj, "_delete_from_sqlite"):
            obj._delete_from_sqlite(self.conn)

    def close(self) -> None:
        self.conn.close()


def init_db() -> None:
    """
    Đọc và thực thi file DB/legal_rag_schema_sqlite.sql để tạo đủ 8 bảng,
    các ràng buộc khóa ngoại, index và trigger cập nhật updated_at.
    """
    conn = _open_raw_sqlite()
    try:
        if settings.SQLITE_SCHEMA_PATH.exists():
            sql_script = settings.SQLITE_SCHEMA_PATH.read_text(encoding="utf-8")
            conn.executescript(sql_script)
        elif HAS_SQLALCHEMY:
            Base.metadata.create_all(bind=engine)
        conn.commit()
    finally:
        conn.close()


def open_session():
    """Mở một database session mới."""
    if HAS_SQLALCHEMY:
        return SessionLocal()
    return FallbackSQLiteSession()


def get_db() -> Generator[Any, None, None]:
    """Dependency cung cấp DB session cho các FastAPI route."""
    db = open_session()
    try:
        yield db
    finally:
        db.close()
