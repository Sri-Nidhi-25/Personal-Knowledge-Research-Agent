"""Document Ingestion Service: Parsing, Metadata Extraction, Hashing, and Storage."""
import hashlib
import io
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import pypdf
from backend.app.storage.filesystem import fs_store
from backend.app.storage.sqlite_db import SessionLocal, DBDocument, DBChunk
from backend.app.models.schemas import Document


class IngestionService:
    @staticmethod
    def compute_sha256(content: bytes) -> str:
        """Compute SHA-256 hash of binary content."""
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def extract_text_and_metadata(
        filename: str, content: bytes
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Extract text and metadata from supported file formats (.md, .txt, .pdf).
        Returns (extracted_text, source_type, metadata_dict).
        """
        path = Path(filename)
        suffix = path.suffix.lower()
        metadata: Dict[str, Any] = {
            "original_filename": filename,
            "file_size_bytes": len(content),
            "extension": suffix
        }

        if suffix in [".md", ".markdown"]:
            source_type = "markdown"
            text = content.decode("utf-8", errors="replace")
        elif suffix in [".txt", ".text"]:
            source_type = "txt"
            text = content.decode("utf-8", errors="replace")
        elif suffix == ".pdf":
            source_type = "pdf"
            try:
                reader = pypdf.PdfReader(io.BytesIO(content))
                pages_text = []
                for i, page in enumerate(reader.pages):
                    page_text = page.extract_text() or ""
                    pages_text.append(page_text)
                text = "\n\n".join(pages_text)
                metadata["page_count"] = len(reader.pages)
            except Exception as e:
                raise ValueError(f"Failed to parse PDF {filename}: {str(e)}")
        else:
            source_type = "other"
            text = content.decode("utf-8", errors="replace")

        # Basic text cleaning / normalization
        text = text.strip()
        metadata["char_count"] = len(text)
        metadata["word_count"] = len(text.split())

        return text, source_type, metadata

    @classmethod
    def ingest_document(
        cls,
        filename: str,
        content: bytes,
        title: Optional[str] = None,
        custom_metadata: Optional[Dict[str, Any]] = None,
        subfolder: Optional[str] = None,
    ) -> Document:
        """
        Ingest, parse, store, and register a document in SQLite.
        """
        content_hash = cls.compute_sha256(content)
        db = SessionLocal()
        try:
            # Check for existing document with identical content hash
            existing = db.query(DBDocument).filter(DBDocument.content_hash == content_hash).first()
            if existing:
                doc_title = title or existing.title
                existing.title = doc_title
                existing.updated_at = datetime.utcnow().isoformat()
                db.commit()
                db.refresh(existing)
                import json
                return Document(
                    document_id=existing.document_id,
                    title=existing.title,
                    source_type=existing.source_type,
                    file_path=existing.file_path,
                    content_hash=existing.content_hash,
                    status=existing.status,
                    created_at=existing.created_at,
                    updated_at=existing.updated_at,
                    metadata=json.loads(existing.metadata_json or "{}")
                )

            # Extract content and metadata
            extracted_text, source_type, metadata = cls.extract_text_and_metadata(filename, content)
            if custom_metadata:
                metadata.update(custom_metadata)
            if subfolder:
                metadata["folder"] = subfolder

            doc_id = f"doc_{uuid.uuid4().hex[:10]}"
            doc_title = title or Path(filename).stem.replace("_", " ").replace("-", " ").title()

            # Determine saved file path
            existing_path = custom_metadata.get("existing_path") if custom_metadata else None
            if existing_path and Path(existing_path).exists():
                saved_path = Path(existing_path)
            else:
                saved_path = fs_store.save_raw_document(filename, content, subfolder=subfolder)

            # Register in SQLite
            import json
            now_iso = datetime.now(timezone.utc).isoformat()
            db_doc = DBDocument(
                document_id=doc_id,
                title=doc_title,
                source_type=source_type,
                file_path=str(saved_path),
                content_hash=content_hash,
                status="available",
                raw_content=extracted_text,
                metadata_json=json.dumps(metadata),
                created_at=now_iso,
                updated_at=now_iso
            )
            db.add(db_doc)
            db.commit()
            db.refresh(db_doc)

            # Auto-index: chunk + embed + upsert into vector store + extract concepts
            try:
                from backend.app.knowledge.index_service import knowledge_index
                from backend.app.knowledge.knowledge_repr import kr_service
                knowledge_index.index_document(
                    document_id=doc_id,
                    text=extracted_text,
                    source_type=source_type,
                    metadata=metadata,
                )
                kr_service.extract_and_store_concepts_from_text(
                    text=extracted_text,
                    document_id=doc_id,
                    source_label=doc_title,
                )
            except Exception as idx_err:
                import logging
                logging.getLogger("app.ingestion").warning(
                    "Auto-indexing / concept extraction failed for %s: %s", doc_id, idx_err
                )

            return Document(
                document_id=db_doc.document_id,
                title=db_doc.title,
                source_type=db_doc.source_type,
                file_path=db_doc.file_path,
                content_hash=db_doc.content_hash,
                status=db_doc.status,
                created_at=db_doc.created_at,
                updated_at=db_doc.updated_at,
                metadata=metadata
            )
        finally:
            db.close()

    @classmethod
    def get_document(cls, document_id: str) -> Optional[Tuple[Document, str]]:
        """Retrieve document metadata and raw text content."""
        db = SessionLocal()
        try:
            db_doc = db.query(DBDocument).filter(DBDocument.document_id == document_id).first()
            if not db_doc:
                return None
            import json
            doc = Document(
                document_id=db_doc.document_id,
                title=db_doc.title,
                source_type=db_doc.source_type,
                file_path=db_doc.file_path,
                content_hash=db_doc.content_hash,
                status=db_doc.status,
                created_at=db_doc.created_at,
                updated_at=db_doc.updated_at,
                metadata=json.loads(db_doc.metadata_json or "{}")
            )
            return doc, db_doc.raw_content or ""
        finally:
            db.close()

    @classmethod
    def list_documents(
        cls,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[list, int]:
        """List documents with optional status filtering."""
        db = SessionLocal()
        try:
            query = db.query(DBDocument)
            if status:
                query = query.filter(DBDocument.status == status)
            total = query.count()
            db_docs = query.order_by(DBDocument.created_at.desc()).offset(offset).limit(limit).all()
            
            import json
            items = [
                Document(
                    document_id=d.document_id,
                    title=d.title,
                    source_type=d.source_type,
                    file_path=d.file_path,
                    content_hash=d.content_hash,
                    status=d.status,
                    created_at=d.created_at,
                    updated_at=d.updated_at,
                    metadata=json.loads(d.metadata_json or "{}")
                )
                for d in db_docs
            ]
            return items, total
        finally:
            db.close()

    @classmethod
    def delete_document(cls, document_id: str) -> bool:
        """Delete a document and its chunks from SQLite and filesystem."""
        db = SessionLocal()
        try:
            db_doc = db.query(DBDocument).filter(DBDocument.document_id == document_id).first()
            if not db_doc:
                return False
            # Remove associated chunks from SQLite
            db.query(DBChunk).filter(DBChunk.document_id == document_id).delete()
            db.delete(db_doc)
            db.commit()

            # Remove associated vectors from ChromaDB
            try:
                from backend.app.storage.chroma_store import chroma_store
                chroma_store.delete_document_chunks(document_id)
            except Exception:
                pass

            return True
        finally:
            db.close()

    @classmethod
    def ingest_directory(cls, directory_path: str) -> Dict[str, Any]:
        """
        Scan a local directory on disk and batch-ingest all supported files (.md, .txt, .pdf).
        """
        from pathlib import Path
        folder = Path(directory_path)
        if not folder.exists() or not folder.is_dir():
            raise ValueError(f"Directory not found: {directory_path}")

        supported_exts = {".md", ".markdown", ".txt", ".pdf"}
        documents = []
        errors = []
        scanned = 0

        for file_path in folder.rglob("*"):
            if not file_path.is_file():
                continue
            
            # Skip hidden files, system dirs, and research subdirectories
            parts_lower = [p.lower() for p in file_path.parts]
            if any(p in ("research", ".research", ".git", "__pycache__", ".vscode", "node_modules") for p in parts_lower[:-1]):
                continue

            # Skip auto-generated research notes so only user original documents are ingested for gap analysis
            if file_path.name.lower().startswith("research_") or file_path.name.startswith("."):
                continue

            if file_path.suffix.lower() in supported_exts:
                scanned += 1
                try:
                    content = file_path.read_bytes()
                    doc = cls.ingest_document(
                        filename=file_path.name,
                        content=content,
                        title=file_path.stem.replace("_", " ").replace("-", " ").title(),
                        custom_metadata={
                            "relative_path": str(file_path.relative_to(folder)),
                            "existing_path": str(file_path.resolve()),
                        },
                        subfolder=folder.name if folder.name != "documents" else None,
                    )
                    documents.append(doc)
                except Exception as err:
                    errors.append(f"{file_path.name}: {str(err)}")

        return {
            "directory": str(folder.resolve()),
            "scanned_files": scanned,
            "ingested_count": len(documents),
            "failed_count": len(errors),
            "documents": documents,
            "errors": errors,
        }


ingestion_service = IngestionService()
