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
from backend.app.storage.sqlite_db import SessionLocal, DBDocument, DBChunk
import json


class KnowledgeIndexService:

    MAX_INDEX_RETRIES = 3

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

        If any step fails (chunking, embedding, Chroma upsert, or SQLite persistence),
        partial work is cleaned up and the entire document is retried from scratch.
        After MAX_INDEX_RETRIES failures, the error is logged and re-raised so the
        caller (ingestion service) can handle it gracefully.
        """
        import logging
        logger = logging.getLogger("app.index_service")

        if not text or not text.strip():
            return []

        meta = metadata or {}
        last_error = None

        for attempt in range(1, KnowledgeIndexService.MAX_INDEX_RETRIES + 1):
            created_chunk_ids: List[str] = []
            try:
                # 1. Chunk the text
                chunks = text_chunker.chunk_text(
                    text=text,
                    source_type=source_type,
                    document_id=document_id,
                    metadata=meta,
                )

                if not chunks:
                    return []

                created_chunk_ids = [c["chunk_id"] for c in chunks]

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
                    chunk_ids=created_chunk_ids,
                    documents=texts,
                    metadatas=chroma_metadatas,
                    embeddings=embeddings,
                )

                # 5. Persist chunk rows in SQLite
                store_chunks(chunks, document_id)

                if attempt > 1:
                    logger.info(
                        "index_document succeeded on retry %d for '%s' (%d chunks)",
                        attempt, document_id, len(created_chunk_ids),
                    )
                return created_chunk_ids

            except Exception as e:
                last_error = e
                logger.warning(
                    "index_document attempt %d/%d failed for '%s': %s — "
                    "cleaning up partial work and retrying",
                    attempt, KnowledgeIndexService.MAX_INDEX_RETRIES,
                    document_id, e,
                )

                # Clean up any partial Chroma inserts from this attempt
                if created_chunk_ids:
                    try:
                        chroma_store.delete_document_chunks(document_id)
                    except Exception as cleanup_err:
                        logger.debug(
                            "Chroma cleanup during retry failed for '%s': %s",
                            document_id, cleanup_err,
                        )

                # Clean up any partial SQLite chunk rows from this attempt
                try:
                    cleanup_db = SessionLocal()
                    cleanup_db.query(DBChunk).filter(
                        DBChunk.document_id == document_id
                    ).delete()
                    cleanup_db.commit()
                    cleanup_db.close()
                except Exception as db_cleanup_err:
                    logger.debug(
                        "SQLite chunk cleanup during retry failed for '%s': %s",
                        document_id, db_cleanup_err,
                    )

        # All retries exhausted
        logger.error(
            "index_document: all %d attempts failed for document '%s'. Last error: %s",
            KnowledgeIndexService.MAX_INDEX_RETRIES, document_id, last_error,
        )
        raise RuntimeError(
            f"Failed to index document '{document_id}' after "
            f"{KnowledgeIndexService.MAX_INDEX_RETRIES} retries. "
            f"Last error: {last_error}"
        )

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
