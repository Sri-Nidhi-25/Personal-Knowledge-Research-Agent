"""
Embedding Service — pluggable provider architecture.

Supported providers (configured via EMBEDDING_PROVIDER in .env):
  - "hash"     : Deterministic hash-based pseudo-embedding (no GPU, always works)
  - "fastembed": FastEmbed local model (small, fast)
  - "sentence-transformers": sentence-transformers library
  - "openai"   : OpenAI text-embedding-3-small / ada-002

The hash provider is the default and requires zero external dependencies.
It produces a 384-dim float32 vector from a SHA-based hash for local testing
and offline usage. Switch to fastembed or sentence-transformers for real
semantic similarity.
"""
import hashlib
import math
import struct
from typing import List

from backend.app.config.settings import settings


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _hash_embed(text: str, dim: int = 384) -> List[float]:
    """
    Deterministic hash-based pseudo-embedding.
    Not semantically meaningful but zero-dependency and reproducible.
    Produces a stable unit-normalised float vector from SHA-256 hashing.
    """
    vec: List[float] = []
    seed = text.encode("utf-8")
    i = 0
    while len(vec) < dim:
        h = hashlib.sha256(seed + i.to_bytes(4, "little")).digest()
        # Unpack 16 unsigned shorts (2 bytes each = 32 bytes total)
        # Map [0, 65535] -> [-1.0, 1.0]
        shorts = struct.unpack("16H", h)
        floats = [(s / 32767.5) - 1.0 for s in shorts]
        vec.extend(floats)
        i += 1

    vec = vec[:dim]
    # L2 normalise
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _get_fastembed_model():
    try:
        from fastembed import TextEmbedding
        return TextEmbedding(model_name=settings.EMBEDDING_MODEL or "BAAI/bge-small-en-v1.5")
    except ImportError:
        raise RuntimeError("fastembed not installed. Run: pip install fastembed")


def _get_st_model():
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(settings.EMBEDDING_MODEL or "all-MiniLM-L6-v2")
    except ImportError:
        raise RuntimeError(
            "sentence-transformers not installed. Run: pip install sentence-transformers"
        )


# Module-level cache for heavy models (loaded once)
_cached_model = None


def _load_model():
    global _cached_model
    if _cached_model is not None:
        return _cached_model
    provider = settings.EMBEDDING_PROVIDER
    if provider == "fastembed":
        _cached_model = _get_fastembed_model()
    elif provider == "sentence-transformers":
        _cached_model = _get_st_model()
    return _cached_model


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def embed_text(text: str) -> List[float]:
    """
    Embed a single piece of text. Returns a list[float] of length EMBEDDING_DIM.
    """
    provider = settings.EMBEDDING_PROVIDER

    if provider == "hash":
        return _hash_embed(text, dim=settings.EMBEDDING_DIM)

    if provider == "fastembed":
        model = _load_model()
        vecs = list(model.embed([text]))
        return vecs[0].tolist()

    if provider == "sentence-transformers":
        model = _load_model()
        vec = model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    if provider == "openai":
        import httpx
        response = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            json={"input": text, "model": settings.EMBEDDING_MODEL or "text-embedding-3-small"},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]

    if provider == "ollama":
        import httpx
        base_url = settings.OLLAMA_BASE_URL or "http://localhost:11434"
        model_name = settings.EMBEDDING_MODEL if settings.EMBEDDING_MODEL and settings.EMBEDDING_MODEL != "default" else settings.OLLAMA_EMBED_MODEL
        try:
            response = httpx.post(
                f"{base_url.rstrip('/')}/api/embeddings",
                json={"model": model_name, "prompt": text},
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()["embedding"]
        except Exception:
            try:
                response = httpx.post(
                    f"{base_url.rstrip('/')}/api/embed",
                    json={"model": model_name, "input": text},
                    timeout=30.0,
                )
                response.raise_for_status()
                return response.json()["embeddings"][0]
            except Exception as e:
                import logging
                logging.getLogger("app.embeddings").warning("Ollama embed error: %s; falling back to hash", e)
                return _hash_embed(text, dim=settings.EMBEDDING_DIM)

    # Default fallback
    return _hash_embed(text, dim=settings.EMBEDDING_DIM)


def embed_batch(texts: List[str]) -> List[List[float]]:
    """
    Embed a batch of texts. Returns a list of embedding vectors.
    Falls back to single embed_text for providers that don't support batching.
    """
    provider = settings.EMBEDDING_PROVIDER

    if provider == "hash":
        return [_hash_embed(t, dim=settings.EMBEDDING_DIM) for t in texts]

    if provider == "fastembed":
        model = _load_model()
        return [v.tolist() for v in model.embed(texts)]

    if provider == "sentence-transformers":
        model = _load_model()
        vecs = model.encode(texts, normalize_embeddings=True, batch_size=64)
        return [v.tolist() for v in vecs]

    # Sequential fallback for openai, ollama, etc.
    return [embed_text(t) for t in texts]
