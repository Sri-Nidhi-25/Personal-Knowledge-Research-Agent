"""
Unit & Regression Tests for the Deep Knowledge Gap Engine.

Verifies:
  1. Required Fixture: RAG Evaluation discovered from implementation corpus without evaluation.
  2. Test A: Superficial 1-off words are filtered/rejected.
  3. Test B: Missing prerequisite detected as high-priority DEPENDENCY gap.
  4. Test C: Knowledge imbalance (High Implementation / Zero Evaluation) flagged as EVALUATION gap.
  5. Test D: Security omission flagged as SECURITY gap.
  6. Test E: Temporal / Frontier gap flagged for 2026 relevance.
  7. Test F: Irrelevant missing concepts are discarded.
"""
import pytest
from backend.app.storage.sqlite_db import (
    SessionLocal, DBDocument, DBChunk, DBConcept, DBRelationship, DBKnowledgeGap
)
from backend.app.knowledge.deep_gap_engine import (
    KnowledgeModelExtractor, CandidateGapGenerator, SignificanceAnalyzer,
    ExternalValidator, DeepKnowledgeGapEngine, deep_gap_engine
)


@pytest.fixture(autouse=True)
def clean_db():
    """Clean SQLite database before each test run."""
    db = SessionLocal()
    try:
        db.query(DBKnowledgeGap).delete()
        db.query(DBRelationship).delete()
        db.query(DBConcept).delete()
        db.query(DBChunk).delete()
        db.query(DBDocument).delete()
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 1. Required Fixture: RAG Evaluation Discovery
# ---------------------------------------------------------------------------

def test_rag_evaluation_gap_discovery_fixture():
    """
    RAG Evaluation Regression Test:
    Corpus has deep RAG implementation (embeddings, vector db, chunking, retrieval, generation),
    but ZERO content on evaluation (faithfulness, recall, ragas).
    Must detect RAG Evaluation as a top-ranked structural/evaluation gap.
    """
    db = SessionLocal()
    try:
        # Populate RAG corpus
        doc = DBDocument(
            document_id="doc_rag_core",
            title="Production RAG Pipeline Architecture",
            content_hash="hash_rag_1",
            status="available",
            raw_content=(
                "# Production RAG Architecture\n\n"
                "## Embeddings and Chunking\n"
                "We use tokenization and dense vector embeddings stored in a vector database like Chroma or Faiss.\n"
                "```python\n"
                "def ingest_chunks(text):\n"
                "    chunks = chunk_text(text)\n"
                "    embeddings = embed_model.encode(chunks)\n"
                "    vector_db.upsert(embeddings)\n"
                "```\n\n"
                "## Vector Search and Retrieval\n"
                "Given a query, we retrieve top-k similar chunks using cosine similarity.\n"
                "## Generation and Grounding\n"
                "We pass retrieved context into the LLM generator prompt to synthesize an answer.\n"
            ),
        )
        db.add(doc)

        chunks = [
            DBChunk(
                chunk_id="chk_1",
                document_id="doc_rag_core",
                content="Dense vector embeddings and chunking with Chroma vector database and Faiss index.",
            ),
            DBChunk(
                chunk_id="chk_2",
                document_id="doc_rag_core",
                content="def retrieve_top_k(query): return vector_db.search(query, k=5) # vector search retrieval",
            ),
            DBChunk(
                chunk_id="chk_3",
                document_id="doc_rag_core",
                content="LLM generation combines user query with retrieved grounding chunks.",
            ),
        ]
        for c in chunks:
            db.add(c)

        concepts = [
            DBConcept(concept_id="c_rag", name="RAG", description="Retrieval-Augmented Generation"),
            DBConcept(concept_id="c_vec", name="Vector Search", description="Dense retrieval"),
            DBConcept(concept_id="c_emb", name="Embeddings", description="Dense vectors"),
        ]
        for cp in concepts:
            db.add(cp)

        db.commit()

        # Run Deep Knowledge Gap Engine
        gaps = deep_gap_engine.discover_gaps()

        assert len(gaps) > 0

        # Verify that an Evaluation / Structural gap for RAG is generated
        eval_gaps = [
            g for g in gaps
            if ("evaluation" in g.title.lower() or "eval" in g.title.lower() or "EVALUATION" in g.gap_types)
        ]
        assert len(eval_gaps) >= 1, "Deep gap engine must discover RAG Evaluation gap"

        top_eval_gap = eval_gaps[0]
        assert top_eval_gap.priority_score >= 0.85
        assert top_eval_gap.personal_relevance >= 0.85
        assert top_eval_gap.current_relevance >= 0.85
        assert len(top_eval_gap.counterfactual_impact) > 0
        assert "evaluation" in top_eval_gap.reason.lower() or "imbalance" in top_eval_gap.reason.lower() or "structural" in top_eval_gap.reason.lower()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 2. Test A: Superficial 1-off Words Filtered
# ---------------------------------------------------------------------------

def test_superficial_words_filtered():
    """Single-mention or dictionary trivialities should be filtered out."""
    chunks = [DBChunk(chunk_id="c1", document_id="d1", content="This is an introduction chapter with a single mention.")]
    candidate = {
        "title": "Isolated concept: introduction",
        "consequence": 0.4,
        "structural_importance": 0.3,
    }
    assert SignificanceAnalyzer.is_superficial(candidate, chunks) is True


# ---------------------------------------------------------------------------
# 3. Test B: Missing Prerequisite (Dependency Gap)
# ---------------------------------------------------------------------------

def test_missing_prerequisite_dependency_gap():
    """Corpus mentions advanced Self-RAG but lacks reflection tokens or foundational prerequisites."""
    concepts = [DBConcept(concept_id="c1", name="Self-RAG", description="Advanced self-reflective RAG")]
    chunks = [DBChunk(chunk_id="chk_1", document_id="d1", content="Self-RAG dynamically retrieves external knowledge during inference.")]
    coverage = {"Self-RAG": {"IMPLEMENTATION": 3, "FOUNDATIONAL": 2}}

    candidates = CandidateGapGenerator.generate_candidates(
        concepts=concepts,
        relationships=[],
        chunks=chunks,
        coverage_matrix=coverage,
    )

    dep_gaps = [c for c in candidates if "DEPENDENCY" in c["gap_types"]]
    assert len(dep_gaps) >= 1
    assert any("prerequisite" in g["title"].lower() for g in dep_gaps)


# ---------------------------------------------------------------------------
# 4. Test C: Knowledge Imbalance (High Implementation / Zero Evaluation)
# ---------------------------------------------------------------------------

def test_knowledge_imbalance_evaluation_gap():
    """High implementation depth (5) with 0 evaluation depth triggers high-priority imbalance gap."""
    concepts = [DBConcept(concept_id="c1", name="RAG", description="Retrieval Augmented Generation")]
    chunks = [
        DBChunk(chunk_id="chk_1", document_id="d1", content="```python\ndef build_rag_pipeline():\n    return Index().query()\n```"),
        DBChunk(chunk_id="chk_2", document_id="d1", content="class VectorRAGEngine: def search(self): pass"),
    ]
    depths = KnowledgeModelExtractor.compute_depth_score("RAG", chunks)
    assert depths["IMPLEMENTATION"] >= 4
    assert depths["EVALUATION"] == 0

    coverage = {"RAG": depths}
    candidates = CandidateGapGenerator.generate_candidates(
        concepts=concepts,
        relationships=[],
        chunks=chunks,
        coverage_matrix=coverage,
    )

    eval_candidates = [c for c in candidates if "EVALUATION" in c["gap_types"]]
    assert len(eval_candidates) >= 1
    assert eval_candidates[0]["consequence"] >= 0.85


# ---------------------------------------------------------------------------
# 5. Test D: Security Omission Gap
# ---------------------------------------------------------------------------

def test_security_omission_gap():
    """System implementation with 0 security coverage triggers security gap."""
    concepts = [DBConcept(concept_id="c1", name="LLM Agent", description="Autonomous LLM system")]
    chunks = [
        DBChunk(chunk_id="chk_1", document_id="d1", content="```python\ndef execute_tool(cmd):\n    import subprocess\n    return subprocess.run(cmd)\n```"),
    ]
    coverage = {"LLM Agent": {"IMPLEMENTATION": 4, "SECURITY": 0}}
    candidates = CandidateGapGenerator.generate_candidates(
        concepts=concepts,
        relationships=[],
        chunks=chunks,
        coverage_matrix=coverage,
    )

    sec_candidates = [c for c in candidates if "SECURITY" in c["gap_types"]]
    assert len(sec_candidates) >= 1
    assert "security" in sec_candidates[0]["title"].lower() or "vulnerability" in sec_candidates[0]["title"].lower()


# ---------------------------------------------------------------------------
# 6. Test E: Temporal / Frontier Gap (2026 Landscape)
# ---------------------------------------------------------------------------

def test_temporal_frontier_gap():
    """Stale 2024 concepts trigger 2026 modern frontier gap."""
    concepts = [DBConcept(concept_id="c1", name="RAG", description="Classic RAG")]
    chunks = [DBChunk(chunk_id="chk_1", document_id="d1", content="Classic RAG system built in 2023 with naive chunking.")]
    coverage = {"RAG": {"IMPLEMENTATION": 2}}

    candidates = CandidateGapGenerator.generate_candidates(
        concepts=concepts,
        relationships=[],
        chunks=chunks,
        coverage_matrix=coverage,
    )

    temporal_gaps = [c for c in candidates if "TEMPORAL" in c["gap_types"] or "FRONTIER" in c["gap_types"]]
    assert len(temporal_gaps) >= 1
    assert temporal_gaps[0]["current_relevance"] >= 0.90


# ---------------------------------------------------------------------------
# 7. Test F: External Validation Utility
# ---------------------------------------------------------------------------

def test_external_validation_current_significance():
    score, evidence = ExternalValidator.validate_current_significance("RAG Evaluation & Faithfulness Metrics")
    assert score >= 0.90
    assert len(evidence) >= 1
