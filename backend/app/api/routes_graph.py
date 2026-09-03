"""Knowledge Graph and Gap Discovery REST API Routes."""
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Query, Body
from backend.app.models.schemas import (
    Concept, Relationship, KnowledgeGraphResponse, KnowledgeGap,
    GapDetectRequest, GapDetectResponse
)
from backend.app.knowledge.knowledge_repr import kr_service
from backend.app.knowledge.gap_discovery import gap_discovery

import uuid

router = APIRouter(tags=["Knowledge Graph & Gaps"])


# --- Concepts & Graph ---

@router.get("/concepts", response_model=List[Concept])
def list_concepts(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[Concept]:
    """List all known concepts in the knowledge graph."""
    return kr_service.list_concepts(limit=limit, offset=offset)


@router.get("/graph", response_model=Dict[str, Any])
def get_knowledge_graph() -> Dict[str, Any]:
    """Return the full knowledge graph (nodes = concepts, edges = relationships)."""
    return kr_service.get_knowledge_graph()


@router.post("/concepts")
def create_concept(body: Dict[str, Any] = Body(...)) -> Concept:
    """Manually register a concept."""
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Concept name is required")
    return kr_service.upsert_concept(
        name=name,
        description=body.get("description", ""),
        aliases=body.get("aliases", []),
        confidence=body.get("confidence", 1.0),
    )


@router.post("/relationships")
def add_relationship(body: Dict[str, Any] = Body(...)) -> Relationship:
    """Add a directed relationship between two concepts."""
    src = body.get("source_name", "").strip()
    tgt = body.get("target_name", "").strip()
    rel = body.get("relationship_type", "related_to").strip()

    if not src or not tgt:
        raise HTTPException(
            status_code=400, detail="Both source_name and target_name are required"
        )

    return kr_service.add_relationship(
        source_name=src,
        rel_type=rel,
        target_name=tgt,
        confidence=body.get("confidence", 0.8),
        created_by=body.get("created_by", "user"),
    )


# --- Gap Discovery ---

@router.post("/gaps/detect", response_model=GapDetectResponse)
def detect_gaps(request: GapDetectRequest) -> GapDetectResponse:
    """
    Trigger automated knowledge gap detection across the knowledge corpus.
    Returns all identified gap candidates sorted by priority score.
    """
    gaps = gap_discovery.detect_all_gaps()
    return GapDetectResponse(
        run_id=f"gaprun_{uuid.uuid4().hex[:8]}",
        gaps=gaps,
    )


@router.get("/gaps", response_model=List[KnowledgeGap])
def list_gaps(
    status: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> List[KnowledgeGap]:
    """List all known knowledge gaps, optionally filtered by status."""
    return gap_discovery.list_gaps(status=status, limit=limit, offset=offset)


@router.get("/gaps/{gap_id}", response_model=KnowledgeGap)
def get_gap(gap_id: str) -> KnowledgeGap:
    """Retrieve a specific knowledge gap by ID."""
    gap = gap_discovery.get_gap(gap_id)
    if not gap:
        raise HTTPException(status_code=404, detail="Gap not found")
    return gap


@router.post("/gaps")
def create_manual_gap(body: Dict[str, Any] = Body(...)) -> KnowledgeGap:
    """Manually register a knowledge gap for autonomous research."""
    title = body.get("title", "").strip()
    description = body.get("description", "").strip()
    if not title or not description:
        raise HTTPException(
            status_code=400, detail="Both title and description are required"
        )
    return gap_discovery.add_manual_gap(
        title=title,
        description=description,
        gap_type=body.get("gap_type", "missing_concept"),
        priority_score=float(body.get("priority_score", 0.8)),
        reason=body.get("reason", ""),
    )


@router.patch("/gaps/{gap_id}/status")
def update_gap_status(gap_id: str, body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Update the status of a knowledge gap."""
    status = body.get("status", "").strip()
    if not status:
        raise HTTPException(status_code=400, detail="Status is required")
    success = gap_discovery.update_gap_status(gap_id, status)
    if not success:
        raise HTTPException(status_code=404, detail="Gap not found")
    return {"gap_id": gap_id, "status": status}


@router.get("/gaps/coverage/matrix")
def get_coverage_matrix() -> Dict[str, Any]:
    """Retrieve the full Concept x Role depth coverage matrix (0-5 scale)."""
    from backend.app.storage.sqlite_db import SessionLocal, DBConcept, DBChunk
    from backend.app.knowledge.deep_gap_engine import KnowledgeModelExtractor
    db = SessionLocal()
    try:
        concepts = db.query(DBConcept).all()
        chunks = db.query(DBChunk).all()
        matrix = KnowledgeModelExtractor.build_coverage_matrix(concepts, chunks)
        return {
            "matrix": matrix,
            "roles": [
                "FOUNDATIONAL", "MECHANISM", "IMPLEMENTATION", "EVALUATION",
                "LIMITATION", "FAILURE_MODE", "SECURITY", "TRADEOFF", "OPERATIONAL", "TEMPORAL"
            ],
            "total_concepts": len(concepts),
        }
    finally:
        db.close()
