"""
Text Chunking Service - splits extracted document text into overlapping chunks
following section-aware and heading-aware strategies for knowledge-intensive content.

Includes robust error handling: if any individual chunk or section fails during
processing, the entire document is retried with a fallback strategy.
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional

from backend.app.storage.sqlite_db import SessionLocal, DBChunk, DBDocument

logger = logging.getLogger("app.chunking")

# --- Constants ---------------------------------------------------------------
DEFAULT_CHUNK_SIZE = 512        # characters (approximate, not tokens)
DEFAULT_CHUNK_OVERLAP = 80      # characters overlap between adjacent chunks
MAX_CHUNK_SIZE = 1200           # hard cap per chunk
MAX_RETRIES = 3                 # number of times to retry the full document on failure


class ChunkingError(Exception):
    """Raised when chunking fails after all retries."""
    pass


class TextChunker:
    """
    Chunks document text with heading-aware and paragraph-aware splitting.

    Strategy:
    1. Split on Markdown H1/H2/H3 headings — each section becomes a logical unit.
    2. If a section is still too long, split on paragraph boundaries (blank lines).
    3. If a paragraph is still too long, hard-split with overlap.

    Error Handling:
    - If any chunk/section fails, the entire document is retried from scratch.
    - After MAX_RETRIES, falls back to a simple paragraph-only strategy.
    - If all strategies fail, raises ChunkingError with full context.
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
        Chunk document text with retry logic. If any chunk fails during
        processing, the entire document is retried up to MAX_RETRIES times.
        On repeated failure, falls back to a simple paragraph-only strategy.

        Returns a list of chunk dicts:
          {chunk_id, document_id, chunk_index, content, heading, section,
           source_type, metadata, created_at}

        Raises ChunkingError if all retry attempts and fallback fail.
        """
        meta = metadata or {}
        last_error = None

        # --- Attempt 1..MAX_RETRIES with heading-aware strategy ---------------
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                chunks = self._chunk_with_strategy(
                    text, source_type, document_id, meta, use_headings=True
                )
                if attempt > 1:
                    logger.info(
                        "Chunking succeeded on retry %d for document '%s' (%d chunks)",
                        attempt, document_id, len(chunks),
                    )
                return chunks

            except Exception as e:
                last_error = e
                logger.warning(
                    "Chunking attempt %d/%d failed for document '%s': %s — retrying entire document",
                    attempt, MAX_RETRIES, document_id, e,
                )

        # --- Fallback: paragraph-only strategy (no heading splitting) ---------
        logger.warning(
            "All %d heading-aware attempts failed for document '%s'. "
            "Falling back to paragraph-only chunking strategy.",
            MAX_RETRIES, document_id,
        )
        try:
            chunks = self._chunk_with_strategy(
                text, source_type, document_id, meta, use_headings=False
            )
            logger.info(
                "Fallback paragraph-only chunking succeeded for document '%s' (%d chunks)",
                document_id, len(chunks),
            )
            return chunks

        except Exception as fallback_err:
            logger.error(
                "Fallback chunking also failed for document '%s': %s",
                document_id, fallback_err,
            )
            raise ChunkingError(
                f"Failed to chunk document '{document_id}' after {MAX_RETRIES} retries "
                f"and fallback strategy. Last heading-aware error: {last_error}. "
                f"Fallback error: {fallback_err}"
            ) from fallback_err

    # --- Strategy runner (shared by primary and fallback) ---------------------

    def _chunk_with_strategy(
        self,
        text: str,
        source_type: str,
        document_id: str,
        meta: Dict[str, Any],
        use_headings: bool,
    ) -> List[Dict[str, Any]]:
        """
        Execute a single chunking pass. Raises on any error so the caller
        can retry the full document.
        """
        if use_headings and source_type in ("markdown", "txt"):
            raw_sections = self._split_by_headings(text)
        else:
            raw_sections = [("", text)]

        chunks: List[Dict[str, Any]] = []
        idx = 0

        for section_num, (heading, section_text) in enumerate(raw_sections):
            try:
                paragraphs = self._split_paragraphs(section_text.strip())
                for para in paragraphs:
                    sub_chunks = self._hard_split(para)
                    for sub in sub_chunks:
                        content = sub.strip()
                        if not content:
                            continue

                        # Validate chunk integrity before adding
                        if len(content) > MAX_CHUNK_SIZE * 2:
                            logger.warning(
                                "Unusually large chunk (%d chars) in doc '%s' section %d — "
                                "truncating to MAX_CHUNK_SIZE",
                                len(content), document_id, section_num,
                            )
                            content = content[:MAX_CHUNK_SIZE]

                        chunk_id = f"chk_{uuid.uuid4().hex[:12]}"
                        now = datetime.now(timezone.utc).isoformat()
                        chunks.append({
                            "chunk_id": chunk_id,
                            "document_id": document_id,
                            "chunk_index": idx,
                            "content": content,
                            "heading": heading or None,
                            "section": heading or None,
                            "source_type": source_type,
                            "metadata": meta,
                            "created_at": now,
                        })
                        idx += 1

            except Exception as section_err:
                # A single section failure should abort this attempt so
                # the caller retries the *entire* document from scratch.
                raise RuntimeError(
                    f"Chunking failed at section {section_num} "
                    f"(heading='{heading[:60]}...'): {section_err}"
                ) from section_err

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
    """
    Persist chunk dicts into SQLite DBChunk rows. Returns list of chunk_ids.

    Error handling: if any single chunk fails to persist, the entire batch is
    rolled back, all chunks get fresh IDs, and the full document is retried.
    After MAX_RETRIES failures, raises ChunkingError.
    """
    import json

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        db = SessionLocal()
        try:
            chunk_ids = []
            for i, c in enumerate(chunks):
                try:
                    # Regenerate chunk_id on retry attempts to avoid PK conflicts
                    if attempt > 1:
                        c["chunk_id"] = f"chk_{uuid.uuid4().hex[:12]}"

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

                except Exception as chunk_err:
                    # One chunk failed — roll back everything and retry the whole batch
                    logger.warning(
                        "store_chunks: chunk %d/%d (id=%s) failed on attempt %d for doc '%s': %s — "
                        "rolling back and retrying all chunks",
                        i + 1, len(chunks), c.get("chunk_id", "?"),
                        attempt, document_id, chunk_err,
                    )
                    db.rollback()
                    last_error = chunk_err
                    raise  # break out to the outer retry loop

            db.commit()

            if attempt > 1:
                logger.info(
                    "store_chunks succeeded on retry %d for document '%s' (%d chunks)",
                    attempt, document_id, len(chunk_ids),
                )
            return chunk_ids

        except Exception as batch_err:
            last_error = batch_err
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning(
                "store_chunks attempt %d/%d failed for document '%s': %s",
                attempt, MAX_RETRIES, document_id, batch_err,
            )

        finally:
            db.close()

    # All retries exhausted
    logger.error(
        "store_chunks: all %d attempts failed for document '%s'. Last error: %s",
        MAX_RETRIES, document_id, last_error,
    )
    raise ChunkingError(
        f"Failed to persist chunks for document '{document_id}' after "
        f"{MAX_RETRIES} retries. Last error: {last_error}"
    )


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
