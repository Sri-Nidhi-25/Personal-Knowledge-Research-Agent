"""Tests for the full research pipeline: planner → agent → proposal → approval."""
import io
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.agent.research_planner import research_planner
from backend.app.agent.research_agent import research_agent
from backend.app.knowledge.gap_discovery import gap_discovery

client = TestClient(app)


# --- Unit: Research Planner ---

def test_planner_creates_plan_from_gap():
    gap = gap_discovery.add_manual_gap(
        title="Understanding Transformers",
        description="Need to learn how transformer architectures work",
        reason="Core ML concept not covered",
    )
    plan = research_planner.create_plan(gap)
    assert plan.plan_id.startswith("plan_")
    assert len(plan.questions) >= 2
    assert len(plan.search_queries) >= 2
    assert plan.gap_id == gap.gap_id


def test_planner_ad_hoc_query():
    plan = research_planner.create_plan_from_query("How does BERT work?")
    assert plan.plan_id.startswith("plan_")
    assert any("BERT" in q.query_text for q in plan.search_queries)


# --- API: Full Research Flow ---

def test_start_research_with_query():
    res = client.post("/api/v1/research/start", json={"query": "What is gradient descent?"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    assert data["sources_found"] > 0
    assert data["claims_made"] > 0
    assert data.get("proposal_id") is not None


def test_start_research_with_gap():
    # Create a manual gap first
    gap_res = client.post("/api/v1/gaps", json={
        "title": "Neural Network Backpropagation",
        "description": "Need to understand backprop algorithm",
        "reason": "Critical optimization concept",
    })
    assert gap_res.status_code == 200
    gap_id = gap_res.json()["gap_id"]

    res = client.post("/api/v1/research/start", json={"gap_id": gap_id})
    assert res.status_code == 200
    assert res.json()["status"] == "completed"


def test_list_runs():
    res = client.get("/api/v1/research/runs")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
    assert len(res.json()) > 0


def test_list_proposals():
    res = client.get("/api/v1/research/proposals")
    assert res.status_code == 200
    proposals = res.json()
    assert isinstance(proposals, list)
    assert len(proposals) > 0


def test_approve_proposal_ingests_into_kb():
    # Get the first pending proposal
    proposals = client.get("/api/v1/research/proposals").json()
    pending = [p for p in proposals if p["status"] in ("pending_review", "pending_approval")]
    assert len(pending) > 0

    pid = pending[0]["proposal_id"]

    # Approve it
    res = client.post(f"/api/v1/research/proposals/{pid}/action", json={"action": "approve"})
    assert res.status_code == 200
    assert res.json()["status"] == "approved"

    # Check it's now in the knowledge base (via document list)
    resp_data = client.get("/api/v1/documents").json()
    docs = resp_data.get("items", []) if isinstance(resp_data, dict) else resp_data
    research_docs = [d for d in docs if "research" in d.get("title", "").lower() or "proposal" in d.get("title", "").lower()]
    assert len(research_docs) >= 1


def test_reject_proposal():
    # Start another research to get a fresh proposal
    res = client.post("/api/v1/research/start", json={"query": "What are attention heads?"})
    assert res.status_code == 200
    pid = res.json().get("proposal_id")
    if pid:
        rej = client.post(f"/api/v1/research/proposals/{pid}/action", json={
            "action": "reject", "feedback": "Too shallow"
        })
        assert rej.status_code == 200
        assert rej.json()["status"] == "rejected"
