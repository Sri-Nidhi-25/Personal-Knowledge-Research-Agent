"""ChromaDB Vector Store Wrapper for Document Chunks."""
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from backend.app.config.settings import settings


class ChromaStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=str(settings.CHROMA_DIR),
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.collection_name = "knowledge_chunks"
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def add_chunks(
        self,
        chunk_ids: List[str],
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        embeddings: Optional[List[List[float]]] = None
    ) -> None:
        if not chunk_ids:
            return
        clean_metadatas = []
        for m in metadatas:
            clean = {}
            for k, v in m.items():
                if isinstance(v, (str, int, float, bool)):
                    clean[k] = v
                else:
                    clean[k] = str(v)
            clean_metadatas.append(clean)

        kwargs: Dict[str, Any] = {
            "ids": chunk_ids,
            "documents": documents,
            "metadatas": clean_metadatas
        }
        if embeddings:
            kwargs["embeddings"] = embeddings

        try:
            self.collection.upsert(**kwargs)
        except Exception as e:
            if "dimension" in str(e).lower() or "expecting" in str(e).lower():
                try:
                    self.client.delete_collection(name=self.collection_name)
                except Exception:
                    pass
                self.collection = self.client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"}
                )
                self.collection.upsert(**kwargs)
            else:
                raise e

    def search(
        self,
        query_text: str,
        query_embedding: Optional[List[float]] = None,
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        kwargs: Dict[str, Any] = {
            "n_results": top_k
        }
        if query_embedding is not None:
            kwargs["query_embeddings"] = [query_embedding]
        else:
            kwargs["query_texts"] = [query_text]

        if where:
            kwargs["where"] = where

        results = self.collection.query(**kwargs)
        output = []
        if results and results.get("ids") and len(results["ids"]) > 0 and len(results["ids"][0]) > 0:
            ids = results["ids"][0]
            docs = results["documents"][0] if results.get("documents") else ["" for _ in ids]
            metas = results["metadatas"][0] if results.get("metadatas") else [{} for _ in ids]
            distances = results["distances"][0] if results.get("distances") else [0.0 for _ in ids]
            for cid, doc, meta, dist in zip(ids, docs, metas, distances):
                similarity = 1.0 - max(0.0, min(1.0, dist)) if dist is not None else 1.0
                output.append({
                    "chunk_id": cid,
                    "document_id": meta.get("document_id", ""),
                    "content": doc,
                    "similarity": similarity,
                    "metadata": meta
                })
        return output

    def delete_document_chunks(self, document_id: str) -> None:
        try:
            self.collection.delete(where={"document_id": document_id})
        except Exception:
            pass

    def count(self) -> int:
        return self.collection.count()


chroma_store = ChromaStore()
