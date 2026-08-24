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


fs_store = FilesystemStore()
