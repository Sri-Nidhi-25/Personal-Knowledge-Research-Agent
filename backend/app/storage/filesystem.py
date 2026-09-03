"""Filesystem Storage Manager for Raw Documents and Knowledge Notes."""
from pathlib import Path
from typing import Optional, List, Dict, Any
from backend.app.config.settings import settings


class FilesystemStore:
    def __init__(self):
        self.doc_dir = Path(settings.DOCUMENTS_DIR)
        self.kb_dir = Path(settings.KNOWLEDGE_DIR)
        self.doc_dir.mkdir(parents=True, exist_ok=True)
        self.kb_dir.mkdir(parents=True, exist_ok=True)

    def save_raw_document(self, filename: str, content: bytes, subfolder: Optional[str] = None) -> Path:
        safe_name = Path(filename).name
        target_dir = self.doc_dir / subfolder if subfolder else self.doc_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / safe_name
        with open(target, 'wb') as f:
            f.write(content)
        return target

    def read_raw_document(self, file_path: str) -> Optional[bytes]:
        target = Path(file_path)
        if not target.is_absolute():
            target = settings.BASE_DIR / target
        if target.exists() and target.is_file():
            with open(target, 'rb') as f:
                return f.read()
        return None

    def save_knowledge_note(self, title: str, markdown_content: str, category: str = "concepts") -> Path:
        safe_title = "_".join(title.lower().split()) + ".md"
        cat_dir = self.kb_dir / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        target = cat_dir / safe_title
        with open(target, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        return target

    def list_knowledge_notes(self) -> List[Dict[str, Any]]:
        notes = []
        for p in self.kb_dir.rglob('*.md'):
            notes.append({
                "title": p.stem.replace('_', ' ').title(),
                "path": str(p.relative_to(settings.BASE_DIR) if p.is_relative_to(settings.BASE_DIR) else p),
                "category": p.parent.name
            })
        return notes

    def save_research_to_destinations(
        self,
        title: str,
        content: str,
        run_id: str,
        gap_id: Optional[str] = None
    ) -> List[Path]:
        """
        Saves the research markdown report to two places:
          1. The dedicated research folder (data/documents/research and data/knowledge/research)
          2. The original folder from which the analysed source documents came from.
        Returns the list of all file paths written.
        """
        import re
        import json
        import logging
        logger = logging.getLogger("app.storage.filesystem")

        clean_title = title.replace("Knowledge Proposal: ", "").replace("Proposal: ", "").replace("Research: ", "").strip()
        safe_slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", clean_title.lower()).strip("_")
        filename = f"research_{safe_slug}.md" if safe_slug else f"research_{run_id}.md"

        saved_paths: List[Path] = []

        # 1. Save to dedicated Research folders
        research_dirs = [
            self.doc_dir / "research",
            self.kb_dir / "research"
        ]
        for r_dir in research_dirs:
            try:
                r_dir.mkdir(parents=True, exist_ok=True)
                target = r_dir / filename
                with open(target, 'w', encoding='utf-8') as f:
                    f.write(content)
                saved_paths.append(target)
                logger.info("Saved research markdown to research folder: %s", target)
            except Exception as e:
                logger.error("Failed writing research markdown to %s: %s", r_dir, e)

        # 2. Identify the origin folders of analyzed documents from SQLite DB
        origin_folders = set()
        try:
            from backend.app.storage.sqlite_db import SessionLocal, DBDocument
            db = SessionLocal()
            try:
                docs = db.query(DBDocument).filter(DBDocument.status == "available").all()
                for d in docs:
                    # Check metadata_json for original existing_path if ingested from folder
                    if d.metadata_json:
                        try:
                            meta = json.loads(d.metadata_json)
                            if meta.get("existing_path"):
                                ep = Path(meta["existing_path"]).parent
                                if ep.exists() and ep.is_dir():
                                    origin_folders.add(ep)
                        except Exception:
                            pass
                    # Also check file_path parent if valid directory
                    if d.file_path:
                        try:
                            fp = Path(d.file_path).parent
                            if fp.exists() and fp.is_dir() and "research" not in fp.name.lower():
                                origin_folders.add(fp)
                        except Exception:
                            pass
            finally:
                db.close()
        except Exception as err:
            logger.warning("Could not query document origin folders: %s", err)

        # Write to all identified source origin folders
        for folder in origin_folders:
            try:
                target = folder / filename
                with open(target, 'w', encoding='utf-8') as f:
                    f.write(content)
                saved_paths.append(target)
                logger.info("Saved research markdown to origin document folder: %s", target)
            except Exception as e:
                logger.error("Failed writing research markdown to origin folder %s: %s", folder, e)

        return saved_paths


fs_store = FilesystemStore()

