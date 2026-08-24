"""API integration tests for knowledge search and indexing endpoints."""
import io
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def _upload_doc(content: bytes, filename: str, title: str) -> str:
    """Helper: upload a document, return its document_id."""
    res = client.post(
        "/api/v1/documents",
        files={"file": (filename, io.BytesIO(content), "text/markdown")},
        data={"title": title},
    )
    assert res.status_code == 200, res.text
    return res.json()["document_id"]


def test_knowledge_stats_endpoint():
    res = client.get("/api/v1/knowledge/stats")
    assert res.status_code == 200
    data = res.json()
    assert "total_documents" in data
    assert "total_vectors_chroma" in data


def test_knowledge_search_after_upload():
    md = b"""# Attention Mechanism
The attention mechanism allows neural networks to focus selectively on parts of the input.
Self-attention computes relationships between all positions in a sequence.

## Scaled Dot-Product
The scaled dot-product attention divides by sqrt(d_k) to prevent vanishing gradients.
"""
    doc_id = _upload_doc(md, "attention.md", "Attention Mechanism Notes")

    # Search for uploaded content
    search_res = client.post(
        "/api/v1/knowledge/search",
        json={"query": "attention neural network", "top_k": 3}
    )
    assert search_res.status_code == 200
    results = search_res.json()["results"]
    assert isinstance(results, list)

    # Cleanup
    client.delete(f"/api/v1/documents/{doc_id}")


def test_knowledge_search_empty_query():
    res = client.post("/api/v1/knowledge/search", json={"query": "  ", "top_k": 3})
    assert res.status_code == 400


def test_document_chunks_endpoint():
    md = b"# BERT\n\nBERT is a bidirectional transformer model pretrained on MLM and NSP tasks."
    doc_id = _upload_doc(md, "bert.md", "BERT Overview")

    chunks_res = client.get(f"/api/v1/knowledge/documents/{doc_id}/chunks")
    assert chunks_res.status_code == 200
    data = chunks_res.json()
    assert data["document_id"] == doc_id
    assert data["total_chunks"] >= 1

    # Cleanup
    client.delete(f"/api/v1/documents/{doc_id}")
