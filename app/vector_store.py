"""
Thao tác với Cơ sở dữ liệu Vector ChromaDB (VectorDB theo sơ đồ lớp UML):
- Lưu trữ vector embedding tại thư mục `chroma_db/` với `id` trùng khớp `chunk_id` trong SQLite.
- Tìm kiếm các đoạn văn bản luật gần nhất theo độ tương đồng Cosine (Cosine Similarity).
- Hỗ trợ xóa vector theo `chunk_ids` hoặc `document_id` để đảm bảo tính toàn vẹn (rollback) với SQLite.
- Tự động fallback sang kho vector Cosine bền vững (`chroma_db/local_vectors.json`) nếu môi trường
  chưa cài đặt gói `chromadb`.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from app.config import settings

try:
    import chromadb

    HAS_CHROMADB = True
except ImportError:
    chromadb = None
    HAS_CHROMADB = False


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a <= 1e-12 or norm_b <= 1e-12:
        return 0.0
    return float(dot / (norm_a * norm_b))


class VectorStore:
    """
    Lớp VectorDB / VectorStore theo đúng Sơ đồ lớp UML (Class Diagram):
    - dbId: String
    - type: String
    - connectionString: String
    + storeEmbedding(ids, embeddings, documents, metadatas)
    + search(query_embedding, top_k)
    + delete(ids, document_id)
    """

    def __init__(
        self,
        persist_dir: Path | None = None,
        collection_name: str | None = None,
    ) -> None:
        self.persist_dir: Path = persist_dir or settings.CHROMA_PERSIST_DIR
        self.collection_name: str = collection_name or settings.CHROMA_COLLECTION_NAME
        self.dbId: str = self.collection_name
        self.type: str = "ChromaDB" if HAS_CHROMADB else "ChromaCompatibleCosineStore"
        self.connectionString: str = str(self.persist_dir)

        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._fallback_file: Path = self.persist_dir / "local_vectors.json"
        self._client: Any = None
        self._collection: Any = None

        if HAS_CHROMADB and chromadb is not None:
            try:
                self._client = chromadb.PersistentClient(path=str(self.persist_dir))
                self._collection = self._client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
            except Exception:
                self._client = None
                self._collection = None

    def _load_fallback_data(self) -> dict[str, dict[str, Any]]:
        if not self._fallback_file.exists():
            return {}
        try:
            return json.loads(self._fallback_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_fallback_data(self, data: dict[str, dict[str, Any]]) -> None:
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._fallback_file.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    def storeEmbedding(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Lưu danh sách vector embedding cùng metadata vào ChromaDB."""
        if not ids:
            return

        if self._collection is not None:
            try:
                self._collection.upsert(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas,
                )
                return
            except Exception as exc:
                # Nếu lệch số chiều vector do đổi model embedding, tạo lại collection
                if "dimension" in str(exc).lower() and self._client is not None:
                    self._client.delete_collection(self.collection_name)
                    self._collection = self._client.get_or_create_collection(
                        name=self.collection_name,
                        metadata={"hnsw:space": "cosine"},
                    )
                    self._collection.upsert(
                        ids=ids,
                        embeddings=embeddings,
                        documents=documents,
                        metadatas=metadatas,
                    )
                    return
                raise

        store = self._load_fallback_data()
        for cid, emb, doc, meta in zip(ids, embeddings, documents, metadatas):
            store[cid] = {
                "id": cid,
                "embedding": emb,
                "document": doc,
                "metadata": meta,
            }
        self._save_fallback_data(store)

    def search(
        self,
        query_embedding: list[float],
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Tìm top_k đoạn văn bản có độ tương đồng Cosine cao nhất với query_embedding.
        Trả về danh sách: [{ chunk_id, document_id, content, metadata, score }, ...]
        """
        k = top_k or settings.RAG_TOP_K

        if self._collection is not None:
            total = self._collection.count()
            if total == 0:
                return []
            n_results = min(k, total)
            res = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                include=["documents", "metadatas", "distances"],
            )
            ids_list = (res.get("ids") or [[]])[0]
            docs_list = (res.get("documents") or [[]])[0]
            metas_list = (res.get("metadatas") or [[]])[0]
            dists_list = (res.get("distances") or [[]])[0]

            results: list[dict[str, Any]] = []
            for cid, doc_text, meta, dist in zip(
                ids_list, docs_list, metas_list, dists_list
            ):
                # Trong ChromaDB với hnsw:space = "cosine", cosine distance = 1 - cosine_similarity
                similarity = max(0.0, min(1.0, 1.0 - float(dist)))
                meta = meta or {}
                results.append(
                    {
                        "chunk_id": cid,
                        "document_id": meta.get("document_id", ""),
                        "content": doc_text or "",
                        "metadata": meta,
                        "score": round(similarity, 4),
                    }
                )
            results.sort(key=lambda x: x["score"], reverse=True)
            return results

        store = self._load_fallback_data()
        if not store:
            return []

        scored: list[dict[str, Any]] = []
        for cid, item in store.items():
            emb = item.get("embedding") or []
            sim = _cosine_similarity(query_embedding, emb)
            meta = item.get("metadata") or {}
            scored.append(
                {
                    "chunk_id": cid,
                    "document_id": meta.get("document_id", ""),
                    "content": item.get("document", ""),
                    "metadata": meta,
                    "score": round(max(0.0, sim), 4),
                }
            )
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:k]

    def delete(
        self,
        ids: list[str] | None = None,
        document_id: str | None = None,
    ) -> None:
        """Xóa các vector theo danh sách chunk_id hoặc theo document_id (hỗ trợ rollback)."""
        if self._collection is not None:
            if ids:
                self._collection.delete(ids=ids)
            if document_id:
                self._collection.delete(where={"document_id": document_id})
            return

        store = self._load_fallback_data()
        changed = False
        if ids:
            for cid in ids:
                if cid in store:
                    del store[cid]
                    changed = True
        if document_id:
            to_remove = [
                cid
                for cid, val in store.items()
                if (val.get("metadata") or {}).get("document_id") == document_id
            ]
            for cid in to_remove:
                del store[cid]
                changed = True
        if changed:
            self._save_fallback_data(store)

    def count(self) -> int:
        """Trả về tổng số vector đang lưu trong kho."""
        if self._collection is not None:
            return int(self._collection.count())
        return len(self._load_fallback_data())


vector_store = VectorStore()
