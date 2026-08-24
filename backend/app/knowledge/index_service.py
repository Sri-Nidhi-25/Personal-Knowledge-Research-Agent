"""
Knowledge Index Service — orchestrates chunking → embedding → Chroma upsert.

Exposes:
  - index_document(document_id, text, source_type, metadata)  → List[chunk_ids]
  - search_knowledge(query, top_k, filters)                   → List[results]
  - reindex_document(document_id)
"""
from typing import List, Dict, Any, Optional

from backend.app.knowledge.chunking import text_chunker, store_chunks, get_document_chunks
from backend.app.knowledge.embeddings import embed_batch, embed_text
from backend.app.storage.chroma_store import chroma_store
from backend.app.storage.sqlite_db import SessionLocal, DBDocument
import json


class KnowledgeIndexService:

    @staticmethod
    def index_document(
        document_id: str,
        text: str,
        source_type: str = "markdown",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Full pipeline: chunk → embed → upsert to Chroma → persist chunks in SQLite.
        Returns list of chunk_ids created.
        """
        if not text or not text.strip():
            return []

        meta = metadata or {}

        # 1. Chunk the text
        chunks = text_chunker.chunk_text(
            text=text,
            source_type=source_type,
            document_id=document_id,
            metadata=meta,
        )

        if not chunks:
            return []

        # 2. Embed all chunk texts in a single batch
        texts = [c["content"] for c in chunks]
        embeddings = embed_batch(texts)

        # 3. Build Chroma metadata (flat dicts, no nested objects)
        chroma_metadatas = []
        for c in chunks:
            chroma_meta = {
                "document_id": document_id,
                "chunk_index": c["chunk_index"],
                "source_type": c.get("source_type", "markdown"),
            }
            if c.get("heading"):
                chroma_meta["heading"] = c["heading"]
            chroma_metadatas.append(chroma_meta)

        # 4. Upsert into Chroma
        chroma_store.add_chunks(
            chunk_ids=[c["chunk_id"] for c in chunks],
            documents=texts,
            metadatas=chroma_metadatas,
            embeddings=embeddings,
        )

        # 5. Persist chunk rows in SQLite
        store_chunks(chunks, document_id)

        return [c["chunk_id"] for c in chunks]

    @staticmethod
    def search_knowledge(
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search over the knowledge corpus.
        Returns list of { chunk_id, document_id, content, score, metadata }.
        """
        query_embedding = embed_text(query)
        raw_results = chroma_store.search(
            query_text=query,
            query_embedding=query_embedding,
            top_k=top_k,
            where=filters,
        )

        results = []
        for r in raw_results:
            results.append({
                "chunk_id": r["chunk_id"],
                "document_id": r["document_id"],
                "content": r["content"],
                "score": r["similarity"],
                "metadata": r["metadata"],
            })
        return results

    @staticmethod
    def reindex_document(document_id: str) -> List[str]:
        """
        Re-chunk and re-embed a document already stored in SQLite.
        Useful after chunking strategy changes.
        """
        db = SessionLocal()
        try:
            db_doc = db.query(DBDocument).filter(DBDocument.document_id == document_id).first()
            if not db_doc or not db_doc.raw_content:
                return []
            metadata = json.loads(db_doc.metadata_json or "{}")
            return KnowledgeIndexService.index_document(
                document_id=document_id,
                text=db_doc.raw_content,
                source_type=db_doc.source_type,
                metadata=metadata,
            )
        finally:
            db.close()

    @staticmethod
    def get_document_chunk_count(document_id: str) -> int:
        """Return number of chunks indexed for a document."""
        chunks = get_document_chunks(document_id)
        return len(chunks)


knowledge_index = KnowledgeIndexService()
