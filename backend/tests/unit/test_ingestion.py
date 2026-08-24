"""Unit tests for document parsing and ingestion service."""
import pytest
from backend.app.knowledge.ingestion import ingestion_service


def test_markdown_text_extraction():
    md_content = b"# RAG Overview\n\nRetrieval-Augmented Generation combines retrieval with generative LLMs."
    text, source_type, meta = ingestion_service.extract_text_and_metadata("rag.md", md_content)
    assert source_type == "markdown"
    assert "Retrieval-Augmented Generation" in text
    assert meta["char_count"] > 0
    assert meta["word_count"] > 0


def test_txt_text_extraction():
    txt_content = b"Vector databases store dense representations of text for semantic search."
    text, source_type, meta = ingestion_service.extract_text_and_metadata("vectors.txt", txt_content)
    assert source_type == "txt"
    assert "Vector databases" in text
    assert meta["extension"] == ".txt"


def test_content_hashing_consistency():
    content1 = b"Sample text for hashing"
    content2 = b"Sample text for hashing"
    content3 = b"Different text"
    
    hash1 = ingestion_service.compute_sha256(content1)
    hash2 = ingestion_service.compute_sha256(content2)
    hash3 = ingestion_service.compute_sha256(content3)
    
    assert hash1 == hash2
    assert hash1 != hash3


def test_document_ingestion_lifecycle():
    content = b"# Evaluation in AI\n\nEvaluating AI agents requires multi-dimensional benchmarking."
    doc = ingestion_service.ingest_document("eval_notes.md", content, title="AI Evaluation Notes")
    assert doc.document_id.startswith("doc_")
    assert doc.title == "AI Evaluation Notes"
    assert doc.status == "available"

    # Test retrieval
    retrieved = ingestion_service.get_document(doc.document_id)
    assert retrieved is not None
    doc_obj, text = retrieved
    assert "AI Evaluation Notes" == doc_obj.title
    assert "Evaluating AI agents" in text

    # Cleanup
    deleted = ingestion_service.delete_document(doc.document_id)
    assert deleted is True
    assert ingestion_service.get_document(doc.document_id) is None
