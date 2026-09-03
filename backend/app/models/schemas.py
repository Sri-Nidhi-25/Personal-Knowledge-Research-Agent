"""Core Data Models and Pydantic Schemas according to Data and API Specifications."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# --- Document & Chunk Schemas ---
class DocumentBase(BaseModel):
    title: str
    source_type: Literal["markdown", "pdf", "txt", "other"] = "markdown"
    file_path: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentCreate(DocumentBase):
    content: Optional[str] = None


class Document(DocumentBase):
    document_id: str
    content_hash: str
    status: Literal["processing", "available", "failed"] = "processing"
    created_at: str
    updated_at: str


class DocumentListResponse(BaseModel):
    items: List[Document]
    total: int


class Chunk(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    chunk_index: int
    page_number: Optional[int] = None
    section: Optional[str] = None
    heading: Optional[str] = None
    source_type: str = "markdown"
    created_at: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


# --- Knowledge & Semantic Search ---
class KnowledgeSearchResult(BaseModel):
    document_id: str
    chunk_id: str
    content: str
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    filters: Optional[Dict[str, Any]] = None


class KnowledgeSearchResponse(BaseModel):
    results: List[KnowledgeSearchResult]


class Concept(BaseModel):
    concept_id: str
    name: str
    description: str = ""
    aliases: List[str] = Field(default_factory=list)
    confidence: float = 1.0


class Relationship(BaseModel):
    relationship_id: str
    source_id: str
    relationship_type: str = "related_to"
    target_id: str
    confidence: float = 1.0
    created_by: str = "system"
    research_run_id: Optional[str] = None


class KnowledgeGraphNode(BaseModel):
    id: str
    label: str
    type: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeGraphEdge(BaseModel):
    source: str
    target: str
    relationship: str
    confidence: float = 1.0


class KnowledgeGraphResponse(BaseModel):
    nodes: List[KnowledgeGraphNode]
    edges: List[KnowledgeGraphEdge]


# --- Knowledge Gap ---
class KnowledgeGap(BaseModel):
    gap_id: str
    title: str
    description: str
    gap_type: str = "missing_concept"
    gap_types: List[str] = Field(default_factory=list)
    confidence: float = 0.8
    priority_score: float = 0.8
    personal_relevance: float = 0.8
    structural_importance: float = 0.8
    current_relevance: float = 0.8
    consequence: float = 0.8
    counterfactual_impact: str = ""
    evidence_signals: List[str] = Field(default_factory=list)
    coverage_matrix_summary: Dict[str, Any] = Field(default_factory=dict)
    related_concepts: List[str] = Field(default_factory=list)
    status: str = "candidate"
    reason: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class GapDetectRequest(BaseModel):
    scope: str = "all"


class GapDetectResponse(BaseModel):
    run_id: str
    gaps: List[KnowledgeGap]


# --- Research Domain ---
class ResearchChecklistItem(BaseModel):
    item_id: str
    category: str = "Evaluation & Verification"
    title: str
    description: str
    target_query: str = ""
    status: str = "pending"  # "pending", "in_progress", "completed"
    ticked: bool = False
    evidence_count: int = 0
    sources_found: List[str] = Field(default_factory=list)
    key_findings: List[str] = Field(default_factory=list)


class ResearchQuestion(BaseModel):
    question_id: str
    gap_id: str = ""
    question: str
    priority: float = 1.0
    status: str = "open"


class SearchQuery(BaseModel):
    query_id: str
    query_text: str
    search_engine: str = "web"
    priority: float = 1.0
    run_id: str = ""
    purpose: str = ""
    iteration: int = 1


class ResearchPlan(BaseModel):
    plan_id: str
    gap_id: str
    title: str = ""
    topic: str = ""
    questions: List[ResearchQuestion] = Field(default_factory=list)
    checklist: List[ResearchChecklistItem] = Field(default_factory=list)
    search_queries: List[SearchQuery] = Field(default_factory=list)
    max_sources: int = 15
    max_search_depth: int = 3
    status: str = "ready"
    created_at: str = ""


class Source(BaseModel):
    source_id: str
    run_id: str
    url: str
    title: str = ""
    content_snippet: str = ""
    credibility_score: float = 0.7
    status: str = "fetched"
    fetched_at: str = ""
    domain: str = ""
    source_type: str = "web"


class Evidence(BaseModel):
    evidence_id: str
    source_id: str
    run_id: str = ""
    content: str
    evidence_type: str = "statement"
    confidence: float = 0.8
    extracted_at: str = ""


class Claim(BaseModel):
    claim_id: str
    run_id: str = ""
    content: str
    supporting_evidence: List[str] = Field(default_factory=list)
    confidence: float = 0.8
    verification_status: str = "unverified"
    created_at: str = ""


class Verification(BaseModel):
    verification_id: str
    claim_id: str
    status: str = "supported"
    confidence: float = 0.8
    supporting_evidence: List[str] = Field(default_factory=list)
    contradicting_evidence: List[str] = Field(default_factory=list)
    reasoning_summary: str = ""


class ResearchEvent(BaseModel):
    event_id: str
    run_id: str
    event_type: str
    message: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = ""


class ResearchRun(BaseModel):
    run_id: str
    gap_id: str
    plan: Optional[ResearchPlan] = None
    checklist: List[ResearchChecklistItem] = Field(default_factory=list)
    status: str = "queued"
    started_at: str = ""
    completed_at: Optional[str] = None
    sources_found: int = 0
    evidence_extracted: int = 0
    claims_made: int = 0
    proposal_id: Optional[str] = None


class StartResearchRequest(BaseModel):
    gap_id: Optional[str] = None
    query: Optional[str] = None
    max_iterations: Optional[int] = 8
    max_search_queries: Optional[int] = 15


# --- Proposal & Approval ---
class KnowledgeProposal(BaseModel):
    proposal_id: str
    run_id: str
    gap_id: str = ""
    title: str
    content: str
    sources: List[str] = Field(default_factory=list)
    claims: List[str] = Field(default_factory=list)
    status: str = "pending_review"
    created_at: str = ""


class ProposalActionRequest(BaseModel):
    action: str  # "approve", "reject", "revise"
    feedback: Optional[str] = None


# --- Health & System ---
class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "unavailable"]
    version: str
    services: Dict[str, str]
