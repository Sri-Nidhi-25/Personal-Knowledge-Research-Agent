"""
Knowledge Representation Service.

Manages the concept registry and relationship graph extracted from the
user's personal knowledge documents.

Supported operations:
  - Extract concepts from document text (via LLM or rule-based mock)
  - Upsert concepts into SQLite
  - Record relationships between concepts
  - Retrieve the full knowledge graph for gap analysis
"""
import json
import re
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from backend.app.storage.sqlite_db import SessionLocal, DBConcept, DBRelationship
from backend.app.models.schemas import Concept, Relationship


# ---------------------------------------------------------------------------
# Rule-Based (Offline) Concept Extractor
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "to", "of", "in", "for", "on", "with", "as", "by", "from", "at",
    "that", "this", "it", "its", "or", "and", "but", "not", "so", "yet",
    "have", "has", "had", "do", "does", "did", "will", "would", "can",
    "could", "should", "may", "might", "must", "shall", "which", "who",
    "how", "what", "when", "where", "why", "overview", "section", "document",
    "introduction", "summary", "paper", "chapter", "figure", "table", "conclusion",
    "example", "part", "details", "definition", "primary", "secondary", "category",
    "categories", "concept", "concepts", "model", "models", "large", "small",
    "step", "steps", "technique", "techniques", "method", "methods", "result",
    "results", "analysis", "system", "systems", "core", "general", "classification",
    "limitation", "limitations", "manifestation", "manifestations", "factor",
    "factors", "adjustment", "adjustments", "benchmark", "benchmarks", "approach",
    "approaches", "framework", "frameworks", "note", "notes", "type", "types",
    "true", "false", "status", "test", "tests", "first", "second", "third",
    "level", "levels", "data", "text", "output", "input", "process", "various",
    "such", "both", "each", "all", "more", "most", "other", "some", "into", "than",
}

_CONCEPT_PATTERN = re.compile(
    r"\b([A-Z][a-zA-Z0-9]*(?:[\s\-][A-Z][a-zA-Z0-9]*)*)\b"
)


def _extract_candidate_concepts(text: str, max_concepts: int = 20) -> List[str]:
    """
    Rule-based concept extraction with noise filtering.
    Filters out structural boilerplate and generic stopwords.
    """
    raw = _CONCEPT_PATTERN.findall(text)
    seen = set()
    unique = []
    for c in raw:
        cl = c.strip()
        if len(cl) < 4:
            continue
        lower = cl.lower()
        if lower in _STOP_WORDS:
            continue
        # Skip single-word concepts that are generic words
        if " " not in cl and "-" not in cl and lower in _STOP_WORDS:
            continue
        if cl not in seen:
            seen.add(cl)
            unique.append(cl)
        if len(unique) >= max_concepts:
            break
    return unique


# ---------------------------------------------------------------------------
# Concept & Relationship CRUD
# ---------------------------------------------------------------------------

class KnowledgeRepresentationService:

    @staticmethod
    def upsert_concept(
        name: str,
        description: str = "",
        aliases: Optional[List[str]] = None,
        confidence: float = 1.0,
    ) -> Concept:
        """Create or update a concept by name (case-insensitive key)."""
        db = SessionLocal()
        try:
            existing = (
                db.query(DBConcept)
                .filter(DBConcept.name.ilike(name.strip()))
                .first()
            )
            if existing:
                if description and not existing.description:
                    existing.description = description
                if aliases:
                    current = json.loads(existing.aliases_json or "[]")
                    merged = list(set(current + aliases))
                    existing.aliases_json = json.dumps(merged)
                db.commit()
                db.refresh(existing)
                return Concept(
                    concept_id=existing.concept_id,
                    name=existing.name,
                    description=existing.description,
                    aliases=json.loads(existing.aliases_json or "[]"),
                    confidence=existing.confidence,
                )

            concept_id = f"con_{uuid.uuid4().hex[:10]}"
            db_concept = DBConcept(
                concept_id=concept_id,
                name=name.strip(),
                description=description,
                aliases_json=json.dumps(aliases or []),
                confidence=confidence,
            )
            db.add(db_concept)
            db.commit()
            db.refresh(db_concept)
            return Concept(
                concept_id=db_concept.concept_id,
                name=db_concept.name,
                description=db_concept.description,
                aliases=json.loads(db_concept.aliases_json or "[]"),
                confidence=db_concept.confidence,
            )
        finally:
            db.close()

    @staticmethod
    def list_concepts(limit: int = 200, offset: int = 0) -> List[Concept]:
        db = SessionLocal()
        try:
            rows = db.query(DBConcept).offset(offset).limit(limit).all()
            return [
                Concept(
                    concept_id=r.concept_id,
                    name=r.name,
                    description=r.description or "",
                    aliases=json.loads(r.aliases_json or "[]"),
                    confidence=r.confidence,
                )
                for r in rows
            ]
        finally:
            db.close()

    @staticmethod
    def add_relationship(
        source_name: str,
        rel_type: str,
        target_name: str,
        confidence: float = 0.8,
        created_by: str = "system",
        research_run_id: Optional[str] = None,
    ) -> Relationship:
        """Create a directed relationship between two concepts."""
        db = SessionLocal()
        try:
            # Resolve concept IDs (create if missing)
            def _get_or_create(name: str) -> str:
                row = db.query(DBConcept).filter(DBConcept.name.ilike(name)).first()
                if row:
                    return row.concept_id
                cid = f"con_{uuid.uuid4().hex[:10]}"
                db.add(DBConcept(concept_id=cid, name=name, description="", aliases_json="[]"))
                db.flush()
                return cid

            src_id = _get_or_create(source_name)
            tgt_id = _get_or_create(target_name)

            # Prevent duplicates
            dup = (
                db.query(DBRelationship)
                .filter(
                    DBRelationship.source_id == src_id,
                    DBRelationship.relationship_type == rel_type,
                    DBRelationship.target_id == tgt_id,
                )
                .first()
            )
            if dup:
                return Relationship(
                    relationship_id=dup.relationship_id,
                    source_id=dup.source_id,
                    relationship_type=dup.relationship_type,
                    target_id=dup.target_id,
                    confidence=dup.confidence,
                    created_by=dup.created_by,
                    research_run_id=dup.research_run_id,
                )

            rel_id = f"rel_{uuid.uuid4().hex[:10]}"
            db_rel = DBRelationship(
                relationship_id=rel_id,
                source_id=src_id,
                relationship_type=rel_type,
                target_id=tgt_id,
                confidence=confidence,
                created_by=created_by,
                research_run_id=research_run_id,
            )
            db.add(db_rel)
            db.commit()
            db.refresh(db_rel)
            return Relationship(
                relationship_id=db_rel.relationship_id,
                source_id=db_rel.source_id,
                relationship_type=db_rel.relationship_type,
                target_id=db_rel.target_id,
                confidence=db_rel.confidence,
                created_by=db_rel.created_by,
                research_run_id=db_rel.research_run_id,
            )
        finally:
            db.close()

    @staticmethod
    def get_knowledge_graph() -> Dict[str, Any]:
        """Return all concepts + relationships as a graph structure."""
        db = SessionLocal()
        try:
            concepts = db.query(DBConcept).all()
            relationships = db.query(DBRelationship).all()

            concept_map = {c.concept_id: c.name for c in concepts}

            nodes = [
                {"id": c.concept_id, "label": c.name, "type": "concept"}
                for c in concepts
            ]
            edges = [
                {
                    "source": r.source_id,
                    "target": r.target_id,
                    "relationship": r.relationship_type,
                    "confidence": r.confidence,
                    "source_label": concept_map.get(r.source_id, r.source_id),
                    "target_label": concept_map.get(r.target_id, r.target_id),
                }
                for r in relationships
                if r.source_id in concept_map and r.target_id in concept_map
            ]

            return {
                "nodes": nodes,
                "edges": edges,
                "total_concepts": len(nodes),
                "total_relationships": len(edges),
            }
        finally:
            db.close()

    @classmethod
    def extract_and_store_concepts_from_text(
        cls, text: str, document_id: str, source_label: str = "document"
    ) -> List[str]:
        """
        Extract concepts from text, persist them, and link co-occurring concepts in the graph.
        Returns list of concept_ids created or updated.
        """
        raw_concepts = _extract_candidate_concepts(text, max_concepts=15)
        ids = []
        concepts_obj = []
        for name in raw_concepts:
            concept = cls.upsert_concept(name=name, confidence=0.9)
            ids.append(concept.concept_id)
            concepts_obj.append(concept)

        # Form baseline graph connections between primary concept and co-occurring concepts
        if len(concepts_obj) >= 2:
            primary_id = concepts_obj[0].concept_id
            for other in concepts_obj[1:4]:
                cls.add_relationship(primary_id, other.concept_id, "relates_to")

        return ids


kr_service = KnowledgeRepresentationService()
