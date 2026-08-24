"""API Integration tests for Document endpoints."""
import io
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_document_upload_and_management_api():
    # 1. Upload Markdown document
    file_content = b"# Retrieval Architecture\n\nRetrieval models fetch relevant context from corpora."
    file = ("retrieval.md", io.BytesIO(file_content), "text/markdown")

    upload_res = client.post(
        "/api/v1/documents",
        files={"file": file},
        data={"title": "Retrieval Architecture"}
    )
    assert upload_res.status_code == 200
    doc_data = upload_res.json()
    doc_id = doc_data["document_id"]
    assert doc_id.startswith("doc_")
    assert doc_data["title"] == "Retrieval Architecture"

    # 2. List documents
    list_res = client.get("/api/v1/documents")
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert any(d["document_id"] == doc_id for d in items)

    # 3. Get single document
    get_res = client.get(f"/api/v1/documents/{doc_id}")
    assert get_res.status_code == 200
    assert "Retrieval models fetch" in get_res.json()["content"]

    # 4. Delete document
    del_res = client.delete(f"/api/v1/documents/{doc_id}")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # 5. Verify 404 after deletion
    get_after_del = client.get(f"/api/v1/documents/{doc_id}")
    assert get_after_del.status_code == 404


def test_ingest_directory_api(tmp_path):
    # Create temp directory with sample markdown and txt files
    doc1 = tmp_path / "note1.md"
    doc1.write_text("# Graph Algorithms\n\nBreadth-first search traverses level by level.", encoding="utf-8")

    doc2 = tmp_path / "note2.txt"
    doc2.write_text("Depth-first search uses a stack to explore paths deeply.", encoding="utf-8")

    res = client.post("/api/v1/documents/directory", json={"directory_path": str(tmp_path)})
    assert res.status_code == 200
    data = res.json()
    assert data["scanned_files"] == 2
    assert data["ingested_count"] == 2
    assert data["failed_count"] == 0
    assert len(data["documents"]) == 2
