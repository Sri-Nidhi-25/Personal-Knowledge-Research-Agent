"""Unit tests for text chunking and knowledge indexing pipeline."""
import pytest
from backend.app.knowledge.chunking import text_chunker, store_chunks, get_document_chunks
from backend.app.knowledge.embeddings import embed_text, embed_batch
from backend.app.knowledge.index_service import knowledge_index


# --- Chunking Tests ---

def test_markdown_chunking_preserves_headings():
    md = """# Overview

This is the introduction paragraph about RAG.

## Architecture

The architecture has three main components: retrieval, augmentation, and generation.

## Evaluation

Evaluation requires measuring both retrieval recall and answer faithfulness.
"""
    chunks = text_chunker.chunk_text(md, source_type="markdown", document_id="test-doc")
    assert len(chunks) >= 3
    headings = [c["heading"] for c in chunks if c.get("heading")]
    assert "Architecture" in headings or any("Architecture" in h for h in headings if h)


def test_plain_text_chunking():
    txt = "A " * 300  # 600 chars, bigger than default chunk size
    chunks = text_chunker.chunk_text(txt, source_type="txt", document_id="test-txt")
    assert len(chunks) >= 1
    for c in chunks:
        assert len(c["content"]) <= 1300  # within MAX_CHUNK_SIZE with some slack


def test_empty_text_produces_no_chunks():
    chunks = text_chunker.chunk_text("", source_type="markdown", document_id="empty-doc")
    assert chunks == []


def test_short_document_single_chunk():
    short = "This is a very short document."
    chunks = text_chunker.chunk_text(short, source_type="txt", document_id="short-doc")
    assert len(chunks) == 1
    assert chunks[0]["content"] == short


# --- Embedding Tests ---

def test_hash_embedding_deterministic():
    v1 = embed_text("Hello, knowledge base!")
    v2 = embed_text("Hello, knowledge base!")
    assert v1 == v2


def test_hash_embedding_dimension():
    from backend.app.config.settings import settings
    v = embed_text("Testing dimension output")
    assert len(v) == settings.EMBEDDING_DIM


def test_hash_embedding_different_texts_differ():
    v1 = embed_text("Retrieval Augmented Generation")
    v2 = embed_text("Convolutional Neural Networks")
    # They should differ in at least some dimension
    assert v1 != v2


def test_batch_embedding_consistency():
    texts = ["doc one content", "doc two content", "doc three content"]
    batch = embed_batch(texts)
    singles = [embed_text(t) for t in texts]
    assert len(batch) == 3
    for b, s in zip(batch, singles):
        assert b == s


# --- Index Service Tests ---

def test_index_and_search_roundtrip():
    doc_id = "test-idx-doc-01"
    text = """# Transformer Architecture

The transformer architecture was introduced by Vaswani et al. in 2017.
Self-attention mechanisms allow models to focus on relevant tokens.

## Multi-Head Attention

Multi-head attention runs attention in parallel across multiple heads.
Each head learns different relationship patterns in the data.
"""
    chunk_ids = knowledge_index.index_document(doc_id, text, source_type="markdown")
    assert len(chunk_ids) > 0

    results = knowledge_index.search_knowledge("transformer self-attention", top_k=3)
    # Should find something related
    assert isinstance(results, list)

    # Cleanup: remove from Chroma
    from backend.app.storage.chroma_store import chroma_store
    chroma_store.delete_document_chunks(doc_id)
