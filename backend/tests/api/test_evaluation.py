"""Tests for Evaluation and Benchmark API routes and metrics."""
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.evaluation.metrics import metrics
from backend.app.models.schemas import Claim, Evidence, KnowledgeProposal

client = TestClient(app)


def test_metrics_citation_grounding():
    claims = [
        Claim(claim_id="c1", content="Claim 1", supporting_evidence=["e1"]),
        Claim(claim_id="c2", content="Claim 2", supporting_evidence=["e2"]),
        Claim(claim_id="c3", content="Claim 3 without evidence", supporting_evidence=[]),
    ]
    evidence = [
        Evidence(evidence_id="e1", source_id="s1", content="Evidence 1"),
        Evidence(evidence_id="e2", source_id="s2", content="Evidence 2"),
    ]

    score = metrics.compute_citation_grounding(claims, evidence)
    assert score == 0.667 or score == 0.67 or score == 0.666


def test_metrics_proposal_structure():
    proposal = KnowledgeProposal(
        proposal_id="prop_test",
        run_id="run_test",
        title="Test Proposal",
        content=(
            "# Title\n\n"
            "## 1. Executive Summary\nSummary\n\n"
            "## 2. Key Concepts\nConcepts\n\n"
            "## 3. Verified Findings\nFindings [1]\n\n"
            "## 6. Sources & References\nSources\n"
        ),
    )
    result = metrics.evaluate_proposal_structure(proposal)
    assert result["is_valid"] is True
    assert result["completeness_score"] == 1.0


def test_evaluation_benchmark_api():
    res = client.post("/api/v1/eval/run")
    assert res.status_code == 200
    data = res.json()
    assert "suite_id" in data
    assert "average_quality_score" in data
    assert "total_benchmark_cases" in data
    assert data["total_benchmark_cases"] >= 1
    assert data["status"] in ("PASS", "NEEDS_IMPROVEMENT", "FAIL")


def test_evaluation_history_api():
    res = client.get("/api/v1/eval/results")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1
