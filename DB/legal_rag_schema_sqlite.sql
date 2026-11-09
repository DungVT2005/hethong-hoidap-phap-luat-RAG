-- SQLite schema for Legal AI + RAG system
-- Version: 1.0
-- Use this file directly with DB Browser for SQLite.
--
-- Architecture:
--   SQLite (relational data) + Vector DB (embeddings / similarity search)
--
-- Notes:
--   1) UUID values are stored as TEXT in SQLite.
--   2) BOOLEAN values are stored as INTEGER: 0 = false, 1 = true.
--   3) DATETIME uses SQLite's built-in date/time representation.
--   4) Actual embedding vectors should be stored in a dedicated Vector DB
--      such as ChromaDB or Qdrant; this SQLite schema stores the metadata.

PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS users (
    user_id        TEXT PRIMARY KEY,
    full_name      TEXT NOT NULL,
    email          TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL DEFAULT 'USER'
                   CHECK (role IN ('USER', 'ADMIN')),
    status         INTEGER NOT NULL DEFAULT 1
                   CHECK (status IN (0, 1)),
    failed_login_attempts INTEGER DEFAULT 0,
    last_failed_login TEXT,
    locked_until   TEXT,
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_documents (
    document_id    TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    document_type  TEXT,
    issue_date     TEXT,
    issuing_agency TEXT,
    document_url   TEXT,
    content        TEXT,
    file_name      TEXT,
    created_by     TEXT,
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by)
        REFERENCES users(user_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id       TEXT PRIMARY KEY,
    document_id    TEXT NOT NULL,
    chunk_index    INTEGER NOT NULL,
    content        TEXT NOT NULL,
    token_count    INTEGER,
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id, chunk_index),
    FOREIGN KEY (document_id)
        REFERENCES source_documents(document_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS questions (
    question_id    TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    content        TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'PENDING'
                   CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')),
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS answers (
    answer_id      TEXT PRIMARY KEY,
    question_id    TEXT NOT NULL UNIQUE,
    content        TEXT NOT NULL,
    model_name     TEXT,
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (question_id)
        REFERENCES questions(question_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS answer_sources (
    answer_id      TEXT NOT NULL,
    document_id    TEXT NOT NULL,
    chunk_id       TEXT,
    rank_no        INTEGER,
    score          REAL,
    PRIMARY KEY (answer_id, document_id, chunk_id),
    FOREIGN KEY (answer_id)
        REFERENCES answers(answer_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,
    FOREIGN KEY (document_id)
        REFERENCES source_documents(document_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,
    FOREIGN KEY (chunk_id)
        REFERENCES document_chunks(chunk_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_histories (
    history_id     TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    question_id    TEXT NOT NULL,
    answer_id      TEXT,
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,
    FOREIGN KEY (question_id)
        REFERENCES questions(question_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,
    FOREIGN KEY (answer_id)
        REFERENCES answers(answer_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS system_config (
    config_key     TEXT PRIMARY KEY,
    config_value   TEXT NOT NULL,
    updated_by     TEXT,
    updated_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (updated_by)
        REFERENCES users(user_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE
);

-- Indexes for common queries.
CREATE INDEX IF NOT EXISTS idx_questions_user_created
    ON questions(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_histories_user_created
    ON chat_histories(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chunks_document
    ON document_chunks(document_id, chunk_index);

CREATE INDEX IF NOT EXISTS idx_answer_sources_answer
    ON answer_sources(answer_id);

CREATE INDEX IF NOT EXISTS idx_answer_sources_document
    ON answer_sources(document_id);

CREATE INDEX IF NOT EXISTS idx_source_documents_created_by
    ON source_documents(created_by);

-- Keep updated_at current when records are modified.
CREATE TRIGGER IF NOT EXISTS trg_users_updated_at
AFTER UPDATE ON users
FOR EACH ROW
BEGIN
    UPDATE users
       SET updated_at = CURRENT_TIMESTAMP
     WHERE user_id = NEW.user_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_source_documents_updated_at
AFTER UPDATE ON source_documents
FOR EACH ROW
BEGIN
    UPDATE source_documents
       SET updated_at = CURRENT_TIMESTAMP
     WHERE document_id = NEW.document_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_system_config_updated_at
AFTER UPDATE ON system_config
FOR EACH ROW
BEGIN
    UPDATE system_config
       SET updated_at = CURRENT_TIMESTAMP
     WHERE config_key = NEW.config_key;
END;

COMMIT;

-- ============================================================
-- OPTIONAL SAMPLE DATA FOR DEMO
-- Uncomment the INSERT statements below when you want test data.
-- ============================================================
-- INSERT INTO users (user_id, full_name, email, password_hash, role)
-- VALUES ('u001', 'Admin Demo', 'admin@example.com', 'CHANGE_ME', 'ADMIN');
--
-- INSERT INTO users (user_id, full_name, email, password_hash, role)
-- VALUES ('u002', 'User Demo', 'user@example.com', 'CHANGE_ME', 'USER');
