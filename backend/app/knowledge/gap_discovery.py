"""
Knowledge Gap Discovery Service.

Integrates with the DeepKnowledgeGapEngine to identify structural, dependency,
evaluation, security, failure-mode, and temporal knowledge gaps across the user corpus.
Maintains CRUD interfaces and backward compatibility for the API and research pipeline.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from backend.app.storage.sqlite_db import (
    SessionLocal, DBKnowledgeGap, DBConcept, DBRelationship, DBChunk, DBDocument
)
from backend.app.models.schemas import KnowledgeGap
from backend.app.knowledge.deep_gap_engine import deep_gap_engine


class GapDiscoveryService:

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # -----------------------------------------------------------------------
    # Core Gap Detection via DeepKnowledgeGapEngine
    # -----------------------------------------------------------------------

    @classmethod
    def detect_all_gaps(cls) -> List[KnowledgeGap]:
        """
        Run Deep Knowledge Gap Engine across the knowledge base.
        Returns a ranked list of consequential, validated KnowledgeGap objects.
        """
        return deep_gap_engine.discover_gaps()

    # -----------------------------------------------------------------------
    # Gap Persistence & Mapping Helper
    # -----------------------------------------------------------------------

    @classmethod
    def _to_schema(cls, r: DBKnowledgeGap) -> KnowledgeGap:
        """Convert a DBKnowledgeGap record into a KnowledgeGap schema model."""
        return KnowledgeGap(
            gap_id=r.gap_id,
            title=r.title,
            description=r.description or "",
            gap_type=r.gap_type or "missing_concept",
            gap_types=json.loads(getattr(r, "gap_types_json", "[]") or "[]"),
            confidence=r.confidence if r.confidence is not None else 0.8,
            priority_score=r.priority_score if r.priority_score is not None else 0.8,
            personal_relevance=getattr(r, "personal_relevance", 0.8) or 0.8,
            structural_importance=getattr(r, "structural_importance", 0.8) or 0.8,
            current_relevance=getattr(r, "current_relevance", 0.8) or 0.8,
            consequence=getattr(r, "consequence", 0.8) or 0.8,
            counterfactual_impact=getattr(r, "counterfactual_impact", "") or "",
            evidence_signals=json.loads(getattr(r, "evidence_signals_json", "[]") or "[]"),
            coverage_matrix_summary=json.loads(getattr(r, "coverage_matrix_json", "{}") or "{}"),
            related_concepts=json.loads(r.related_concepts_json or "[]"),
            status=r.status or "candidate",
            reason=r.reason or "",
            created_at=r.created_at or cls._now(),
        )

    # -----------------------------------------------------------------------
    # CRUD: Gap Management
    # -----------------------------------------------------------------------

    @classmethod
    def list_gaps(
        cls,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[KnowledgeGap]:
        db = SessionLocal()
        try:
            q = db.query(DBKnowledgeGap)
            if status and status != "all":
                q = q.filter(DBKnowledgeGap.status == status)
            elif not status:
                # By default, exclude resolved gaps from active gap view
                q = q.filter(DBKnowledgeGap.status != "resolved")
            rows = q.order_by(DBKnowledgeGap.priority_score.desc()).offset(offset).limit(limit).all()
            return [cls._to_schema(r) for r in rows]
        finally:
            db.close()

    @classmethod
    def get_gap(cls, gap_id: str) -> Optional[KnowledgeGap]:
        db = SessionLocal()
        try:
            r = db.query(DBKnowledgeGap).filter(DBKnowledgeGap.gap_id == gap_id).first()
            if not r:
                return None
            return cls._to_schema(r)
        finally:
            db.close()

    @staticmethod
    def update_gap_status(gap_id: str, status: str) -> bool:
        db = SessionLocal()
        try:
            r = db.query(DBKnowledgeGap).filter(DBKnowledgeGap.gap_id == gap_id).first()
            if not r:
                return False
            r.status = status
            db.commit()
            return True
        finally:
            db.close()

    @classmethod
    def add_manual_gap(
        cls,
        title: str,
        description: str,
        gap_type: str = "missing_concept",
        priority_score: float = 0.8,
        reason: str = "",
    ) -> KnowledgeGap:
        """Allow users to manually register a knowledge gap for research."""
        db = SessionLocal()
        try:
            gap_id = f"gap_{uuid.uuid4().hex[:10]}"
            now = cls._now()
            db_gap = DBKnowledgeGap(
                gap_id=gap_id,
                title=title,
                description=description,
                gap_type=gap_type,
                gap_types_json=json.dumps([gap_type.upper()]),
                confidence=1.0,  # User-provided gaps have high confidence
                priority_score=priority_score,
                personal_relevance=1.0,
                structural_importance=0.9,
                current_relevance=0.9,
                consequence=0.9,
                counterfactual_impact="User identified this knowledge gap as critical to their workflow.",
                evidence_signals_json=json.dumps(["Manually created by user"]),
                coverage_matrix_json="{}",
                related_concepts_json="[]",
                status="candidate",
                reason=reason or "Manually registered user gap.",
                created_at=now,
            )
            db.add(db_gap)
            db.commit()
            db.refresh(db_gap)
            return cls._to_schema(db_gap)
        finally:
            db.close()


gap_discovery = GapDiscoveryService()
