"""SQLite Database Layer using SQLAlchemy."""
import json
from datetime import datetime
from typing import Generator
from sqlalchemy import create_engine, Column, String, Integer, Float, Text, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.config.settings import settings

Base = declarative_base()


class DBDocument(Base):
    __tablename__ = "documents"
    document_id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    source_type = Column(String, default="markdown")
    file_path = Column(String, nullable=True)
    content_hash = Column(String, index=True)
    status = Column(String, default="processing")
    raw_content = Column(Text, nullable=True)
    metadata_json = Column(Text, default="{}")
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String, default=lambda: datetime.utcnow().isoformat())


class DBChunk(Base):
    __tablename__ = "chunks"
    chunk_id = Column(String, primary_key=True, index=True)
    document_id = Column(String, index=True)
    chunk_index = Column(Integer)
    content = Column(Text, nullable=False)
    page_number = Column(Integer, nullable=True)
    section = Column(String, nullable=True)
    heading = Column(String, nullable=True)
    source_type = Column(String, default="markdown")
    metadata_json = Column(Text, default="{}")
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())


class DBConcept(Base):
    __tablename__ = "concepts"
    concept_id = Column(String, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(Text, default="")
    aliases_json = Column(Text, default="[]")
    confidence = Column(Float, default=1.0)


class DBRelationship(Base):
    __tablename__ = "relationships"
    relationship_id = Column(String, primary_key=True, index=True)
    source_id = Column(String, index=True)
    relationship_type = Column(String, index=True)
    target_id = Column(String, index=True)
    confidence = Column(Float, default=1.0)
    created_by = Column(String, default="system")
    research_run_id = Column(String, nullable=True)


class DBKnowledgeGap(Base):
    __tablename__ = "knowledge_gaps"
    gap_id = Column(String, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text)
    gap_type = Column(String, default="missing_concept")
    confidence = Column(Float, default=0.8)
    priority_score = Column(Float, default=0.8)
    related_concepts_json = Column(Text, default="[]")
    status = Column(String, default="candidate")
    reason = Column(Text, default="")
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())


class DBResearchRun(Base):
    __tablename__ = "research_runs"
    run_id = Column(String, primary_key=True, index=True)
    gap_id = Column(String, index=True)
    plan_json = Column(Text, default="{}")
    status = Column(String, default="queued")
    started_at = Column(String, default=lambda: datetime.utcnow().isoformat())
    completed_at = Column(String, nullable=True)
    iteration = Column(Integer, default=0)
    queries_used = Column(Integer, default=0)
    sources_found = Column(Integer, default=0)
    evidence_extracted = Column(Integer, default=0)
    claims_made = Column(Integer, default=0)
    claims_count = Column(Integer, default=0)
    budget_json = Column(Text, default="{}")
    knowledge_snapshot = Column(Text, default="")
    final_reason = Column(String, nullable=True)


class DBSource(Base):
    __tablename__ = "sources"
    source_id = Column(String, primary_key=True, index=True)
    run_id = Column(String, index=True)
    url = Column(String)
    title = Column(String, default="")
    domain = Column(String, default="")
    content_snippet = Column(Text, default="")
    credibility_score = Column(Float, default=0.7)
    status = Column(String, default="fetched")
    source_type = Column(String, default="web")
    published_at = Column(String, nullable=True)
    retrieved_at = Column(String, default=lambda: datetime.utcnow().isoformat())
    fetched_at = Column(String, default=lambda: datetime.utcnow().isoformat())
    authority_score = Column(Float, default=0.8)
    raw_content = Column(Text, nullable=True)


class DBEvidence(Base):
    __tablename__ = "evidence"
    evidence_id = Column(String, primary_key=True, index=True)
    source_id = Column(String, index=True)
    run_id = Column(String, index=True, default="")
    claim_id = Column(String, nullable=True, index=True)
    content = Column(Text, default="")
    text = Column(Text, default="")
    evidence_type = Column(String, default="statement")
    location = Column(String, default="")
    confidence = Column(Float, default=0.8)
    extracted_at = Column(String, default=lambda: datetime.utcnow().isoformat())


class DBClaim(Base):
    __tablename__ = "claims"
    claim_id = Column(String, primary_key=True, index=True)
    run_id = Column(String, index=True)
    content = Column(Text, default="")
    text = Column(Text, default="")
    source_type = Column(String, default="web_research")
    confidence = Column(Float, default=0.8)
    verification_status = Column(String, default="supported")
    supporting_evidence_json = Column(Text, default="[]")
    supporting_sources_json = Column(Text, default="[]")
    contradicting_sources_json = Column(Text, default="[]")
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())


class DBKnowledgeProposal(Base):
    __tablename__ = "knowledge_proposals"
    proposal_id = Column(String, primary_key=True, index=True)
    run_id = Column(String, index=True)
    gap_id = Column(String, index=True, nullable=True)
    title = Column(String)
    content = Column(Text)
    summary = Column(Text, default="")
    key_concepts_json = Column(Text, default="[]")
    sources_json = Column(Text, default="[]")
    claims_json = Column(Text, default="[]")
    citations_json = Column(Text, default="[]")
    relationships_json = Column(Text, default="[]")
    confidence = Column(Float, default=0.85)
    status = Column(String, default="pending_review")
    feedback = Column(Text, nullable=True)
    review_notes = Column(Text, nullable=True)
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())


class DBResearchEvent(Base):
    __tablename__ = "research_events"
    event_id = Column(String, primary_key=True, index=True)
    run_id = Column(String, index=True)
    timestamp = Column(String, default=lambda: datetime.utcnow().isoformat())
    event_type = Column(String, index=True)
    state = Column(String, default="active")
    message = Column(Text, default="")
    data_json = Column(Text, default="{}")


engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


# Auto-initialize tables on module load
init_db()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
