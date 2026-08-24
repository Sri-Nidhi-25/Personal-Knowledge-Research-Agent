"""
Text Chunking Service - splits extracted document text into overlapping chunks
following section-aware and heading-aware strategies for knowledge-intensive content.
"""
import re
import uuid
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional

from backend.app.storage.sqlite_db import SessionLocal, DBChunk, DBDocument


# --- Constants ---------------------------------------------------------------
DEFAULT_CHUNK_SIZE = 512        # characters (approximate, not tokens)
DEFAULT_CHUNK_OVERLAP = 80      # characters overlap between adjacent chunks
MAX_CHUNK_SIZE = 1200           # hard cap per chunk


class TextChunker:
    """
    Chunks document text with heading-aware and paragraph-aware splitting.

    Strategy:
    1. Split on Markdown H1/H2/H3 headings — each section becomes a logical unit.
    2. If a section is still too long, split on paragraph boundaries (blank lines).
    3. If a paragraph is still too long, hard-split with overlap.
    """

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    # --- Public API -----------------------------------------------------------

    def chunk_text(
        self,
        text: str,
        source_type: str = "markdown",
        document_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Chunk document text. Returns a list of chunk dicts:
          {chunk_id, document_id, chunk_index, content, heading, section,
           source_type, metadata, created_at}
        """
        meta = metadata or {}

        if source_type in ("markdown", "txt"):
            raw_sections = self._split_by_headings(text)
        else:
            # PDF / other: split on paragraph breaks only
            raw_sections = [("", text)]

        chunks: List[Dict[str, Any]] = []
        idx = 0

        for heading, section_text in raw_sections:
            paragraphs = self._split_paragraphs(section_text.strip())
            for para in paragraphs:
                sub_chunks = self._hard_split(para)
                for sub in sub_chunks:
                    if not sub.strip():
                        continue
                    chunk_id = f"chk_{uuid.uuid4().hex[:12]}"
                    now = datetime.utcnow().isoformat()
                    chunks.append({
                        "chunk_id": chunk_id,
                        "document_id": document_id,
                        "chunk_index": idx,
                        "content": sub.strip(),
                        "heading": heading or None,
                        "section": heading or None,
                        "source_type": source_type,
                        "metadata": meta,
                        "created_at": now,
                    })
                    idx += 1

        return chunks

    # --- Internal Helpers -----------------------------------------------------

    def _split_by_headings(self, text: str) -> List[Tuple[str, str]]:
        """Split Markdown text on H1/H2/H3 headings."""
        pattern = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
        matches = list(pattern.finditer(text))

        if not matches:
            return [("", text)]

        sections: List[Tuple[str, str]] = []

        # Text before first heading
        if matches[0].start() > 0:
            preamble = text[: matches[0].start()].strip()
            if preamble:
                sections.append(("", preamble))

        for i, m in enumerate(matches):
            heading_text = m.group(2).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            sections.append((heading_text, body))

        return sections

    def _split_paragraphs(self, text: str) -> List[str]:
        """Split on blank lines (paragraph breaks)."""
        paras = re.split(r"\n\s*\n", text)
        result = []
        for para in paras:
            stripped = para.strip()
            if stripped:
                result.append(stripped)
        return result if result else [text]

    def _hard_split(self, text: str) -> List[str]:
        """Hard-split oversized text with overlap."""
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            # Try to break at last sentence boundary (.?!) within the window
            if end < len(text):
                last_boundary = max(
                    text.rfind(". ", start, end),
                    text.rfind("? ", start, end),
                    text.rfind("! ", start, end),
                    text.rfind("\n", start, end),
                )
                if last_boundary > start:
                    end = last_boundary + 1
            chunks.append(text[start:end])
            start = end - self.chunk_overlap if end < len(text) else end

        return [c for c in chunks if c.strip()]


# Singleton instance
text_chunker = TextChunker()


# --- Persistence helpers ------------------------------------------------------

def store_chunks(
    chunks: List[Dict[str, Any]],
    document_id: str,
) -> List[str]:
    """Persist chunk dicts into SQLite DBChunk rows. Returns list of chunk_ids."""
    import json

    db = SessionLocal()
    try:
        chunk_ids = []
        for c in chunks:
            db_chunk = DBChunk(
                chunk_id=c["chunk_id"],
                document_id=document_id,
                chunk_index=c["chunk_index"],
                content=c["content"],
                heading=c.get("heading"),
                section=c.get("section"),
                source_type=c.get("source_type", "markdown"),
                metadata_json=json.dumps(c.get("metadata", {})),
                created_at=c["created_at"],
            )
            db.merge(db_chunk)
            chunk_ids.append(c["chunk_id"])
        db.commit()
        return chunk_ids
    finally:
        db.close()


def get_document_chunks(document_id: str) -> List[Dict[str, Any]]:
    """Retrieve all chunks for a document from SQLite."""
    import json

    db = SessionLocal()
    try:
        rows = (
            db.query(DBChunk)
            .filter(DBChunk.document_id == document_id)
            .order_by(DBChunk.chunk_index)
            .all()
        )
        return [
            {
                "chunk_id": r.chunk_id,
                "document_id": r.document_id,
                "chunk_index": r.chunk_index,
                "content": r.content,
                "heading": r.heading,
                "section": r.section,
                "source_type": r.source_type,
                "metadata": json.loads(r.metadata_json or "{}"),
                "created_at": r.created_at,
            }
            for r in rows
        ]
    finally:
        db.close()
