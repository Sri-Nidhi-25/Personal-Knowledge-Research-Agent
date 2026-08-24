"""Tests for knowledge representation and gap discovery."""
import io
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.knowledge.knowledge_repr import KnowledgeRepresentationService, _extract_candidate_concepts
from backend.app.knowledge.gap_discovery import GapDiscoveryService

client = TestClient(app)


# --- Unit: Concept Extractor ---

def test_concept_extraction_from_text():
    text = "Transformer Architecture uses Multi-Head Attention and Self-Attention mechanisms."
    concepts = _extract_candidate_concepts(text)
    assert len(concepts) > 0
    names = [c.lower() for c in concepts]
    # Should detect at least the multi-word capitalized names
    assert any("transformer" in n for n in names)


def test_concept_upsert_and_retrieval():
    concept = KnowledgeRepresentationService.upsert_concept(
        name="TestConcept_XYZ_Integration",
        description="A test concept for unit testing",
    )
    assert concept.concept_id.startswith("con_")
    assert concept.name == "TestConcept_XYZ_Integration"

    # Second upsert should not duplicate
    concept2 = KnowledgeRepresentationService.upsert_concept(
        name="TestConcept_XYZ_Integration",
        description="Updated description",
    )
    assert concept2.concept_id == concept.concept_id


def test_relationship_creation():
    rel = KnowledgeRepresentationService.add_relationship(
        source_name="NeuralNet_Test_Src",
        rel_type="related_to",
        target_name="DeepLearning_Test_Tgt",
        created_by="test",
    )
    assert rel.relationship_id.startswith("rel_")
    assert rel.relationship_type == "related_to"

    # Second call should not duplicate
    rel2 = KnowledgeRepresentationService.add_relationship(
        source_name="NeuralNet_Test_Src",
        rel_type="related_to",
        target_name="DeepLearning_Test_Tgt",
        created_by="test",
    )
    assert rel2.relationship_id == rel.relationship_id


# --- API: Graph Endpoints ---

def test_list_concepts_api():
    res = client.get("/api/v1/concepts")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)


def test_knowledge_graph_api():
    res = client.get("/api/v1/graph")
    assert res.status_code == 200
    data = res.json()
    assert "nodes" in data
    assert "edges" in data
    assert "total_concepts" in data


def test_manual_concept_creation_api():
    res = client.post(
        "/api/v1/concepts",
        json={"name": "ManualConcept_API_Test", "description": "Created via API"}
    )
    assert res.status_code == 200
    assert res.json()["name"] == "ManualConcept_API_Test"


def test_gap_detection_api():
    # First ingest a doc to create concepts
    md = b"# Knowledge Graphs\n\nKnowledge Graphs represent structured information in triples."
    client.post(
        "/api/v1/documents",
        files={"file": ("kg.md", io.BytesIO(md), "text/markdown")},
        data={"title": "Knowledge Graph Intro"},
    )

    detect_res = client.post("/api/v1/gaps/detect", json={"scope": "all"})
    assert detect_res.status_code == 200
    data = detect_res.json()
    assert "run_id" in data
    assert "gaps" in data
    assert isinstance(data["gaps"], list)


def test_manual_gap_creation_api():
    res = client.post(
        "/api/v1/gaps",
        json={
            "title": "Understanding RLHF in LLMs",
            "description": "Need to understand reinforcement learning from human feedback",
            "gap_type": "missing_concept",
            "priority_score": 0.9,
            "reason": "RLHF is critical for alignment but not covered in my notes",
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["gap_id"].startswith("gap_")
    assert data["priority_score"] == 0.9

    # Verify in list endpoint
    list_res = client.get("/api/v1/gaps")
    assert list_res.status_code == 200
    gap_ids = [g["gap_id"] for g in list_res.json()]
    assert data["gap_id"] in gap_ids
