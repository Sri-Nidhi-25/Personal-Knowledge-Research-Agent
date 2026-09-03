"""Knowledge Corpus Search & Indexing Routes."""
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Query
from backend.app.models.schemas import KnowledgeSearchRequest, KnowledgeSearchResponse, KnowledgeSearchResult
from backend.app.knowledge.index_service import knowledge_index

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


@router.post("/search", response_model=KnowledgeSearchResponse)
def search_knowledge(request: KnowledgeSearchRequest) -> KnowledgeSearchResponse:
    """
    Semantic search over the entire knowledge corpus.
    Returns the top-k most relevant chunks using vector similarity.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty")

    results = knowledge_index.search_knowledge(
        query=request.query,
        top_k=request.top_k,
        filters=request.filters,
    )

    return KnowledgeSearchResponse(
        results=[
            KnowledgeSearchResult(
                document_id=r["document_id"],
                chunk_id=r["chunk_id"],
                content=r["content"],
                score=r["score"],
                metadata=r["metadata"],
            )
            for r in results
        ]
    )


@router.post("/documents/{document_id}/reindex")
def reindex_document(document_id: str) -> Dict[str, Any]:
    """
    Force re-chunk and re-embed an existing document.
    Useful after updating chunking strategy.
    """
    chunk_ids = knowledge_index.reindex_document(document_id)
    if chunk_ids is None:
        raise HTTPException(status_code=404, detail="Document not found or has no content")

    return {
        "document_id": document_id,
        "chunks_indexed": len(chunk_ids),
        "chunk_ids": chunk_ids[:5],  # Return first 5 for inspection
    }


@router.get("/documents/{document_id}/chunks")
def get_document_chunks(document_id: str) -> Dict[str, Any]:
    """Return all stored chunks for a document."""
    from backend.app.knowledge.chunking import get_document_chunks as _get
    chunks = _get(document_id)
    return {
        "document_id": document_id,
        "total_chunks": len(chunks),
        "chunks": chunks,
    }


@router.get("/stats")
def get_knowledge_stats() -> Dict[str, Any]:
    """Return high-level statistics about the knowledge corpus."""
    from backend.app.storage.chroma_store import chroma_store
    from backend.app.storage.sqlite_db import (
        SessionLocal, DBDocument, DBChunk, DBKnowledgeGap, DBKnowledgeProposal
    )

    db = SessionLocal()
    try:
        doc_count = db.query(DBDocument).count()
        chunk_count = db.query(DBChunk).count()
        available_docs = db.query(DBDocument).filter(DBDocument.status == "available").count()
        vector_count = chroma_store.count()
        
        active_gaps = db.query(DBKnowledgeGap).filter(DBKnowledgeGap.status != "resolved").count()
        resolved_gaps = db.query(DBKnowledgeGap).filter(DBKnowledgeGap.status == "resolved").count()
        pending_proposals = db.query(DBKnowledgeProposal).filter(DBKnowledgeProposal.status == "pending_review").count()
        approved_proposals = db.query(DBKnowledgeProposal).filter(DBKnowledgeProposal.status == "approved").count()

        return {
            "total_documents": doc_count,
            "available_documents": available_docs,
            "total_chunks_sqlite": chunk_count,
            "total_vectors_chroma": vector_count,
            "active_gaps": active_gaps,
            "resolved_gaps": resolved_gaps,
            "total_gaps": active_gaps + resolved_gaps,
            "pending_proposals": pending_proposals,
            "approved_proposals": approved_proposals,
            "total_proposals": pending_proposals + approved_proposals,
        }
    finally:
        db.close()


@router.post("/clear")
def clear_knowledge_base() -> Dict[str, Any]:
    """
    Clear all documents, chunks, concepts, relationships, gaps, runs, and proposals.
    Resets the Chroma vector collection to provide a clean slate.
    """
    from backend.app.storage.chroma_store import chroma_store
    from backend.app.storage.sqlite_db import (
        SessionLocal, DBDocument, DBChunk, DBConcept, DBRelationship,
        DBKnowledgeGap, DBResearchRun, DBSource, DBEvidence, DBClaim,
        DBKnowledgeProposal, DBResearchEvent,
    )

    db = SessionLocal()
    try:
        db.query(DBResearchEvent).delete()
        db.query(DBKnowledgeProposal).delete()
        db.query(DBClaim).delete()
        db.query(DBEvidence).delete()
        db.query(DBSource).delete()
        db.query(DBResearchRun).delete()
        db.query(DBKnowledgeGap).delete()
        db.query(DBRelationship).delete()
        db.query(DBConcept).delete()
        db.query(DBChunk).delete()
        db.query(DBDocument).delete()
        db.commit()

        # Reset Chroma collection
        try:
            chroma_store.client.delete_collection(name="knowledge_chunks")
            chroma_store.collection = chroma_store.client.get_or_create_collection(
                name="knowledge_chunks",
                metadata={"hnsw:space": "cosine"},
            )
        except Exception:
            pass

        # Clean auto-generated files on disk (loose doc_* files and research subfolder contents)
        from pathlib import Path
        from backend.app.config.settings import settings
        for target_dir in [Path(settings.DOCUMENTS_DIR), Path(settings.KNOWLEDGE_DIR), Path("data/knowledge"), Path("data/documents")]:
            if target_dir.exists():
                for f in target_dir.iterdir():
                    if f.is_file() and f.name.startswith("doc_"):
                        f.unlink(missing_ok=True)
                r_dir = target_dir / "research"
                if r_dir.exists():
                    for f in r_dir.iterdir():
                        if f.is_file():
                            f.unlink(missing_ok=True)

        return {
            "success": True,
            "message": "Knowledge base, concepts, gaps, proposals, disk files, and vector index have been completely reset.",
        }
    finally:
        db.close()
