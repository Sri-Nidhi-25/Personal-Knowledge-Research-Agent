"""Document Management REST API Routes."""
from typing import Optional, Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from backend.app.models.schemas import Document, DocumentListResponse
from backend.app.knowledge.ingestion import ingestion_service
from backend.app.storage.chroma_store import chroma_store

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("", response_model=Document)
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
) -> Document:
    """Upload and ingest a personal knowledge document (.md, .pdf, .txt)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename missing")

    try:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        doc = ingestion_service.ingest_document(
            filename=file.filename,
            content=content,
            title=title
        )
        return doc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to ingest document: {str(e)}")


@router.get("", response_model=DocumentListResponse)
def list_documents(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
) -> DocumentListResponse:
    """List all ingested documents with optional status filtering."""
    items, total = ingestion_service.list_documents(status=status, limit=limit, offset=offset)
    return DocumentListResponse(items=items, total=total)


@router.get("/{document_id}")
def get_document(document_id: str) -> Dict[str, Any]:
    """Retrieve document metadata and text content."""
    res = ingestion_service.get_document(document_id)
    if not res:
        raise HTTPException(status_code=404, detail="Document not found")
    doc, raw_content = res
    return {
        "document": doc,
        "content": raw_content
    }


@router.delete("/{document_id}")
def delete_document(document_id: str) -> Dict[str, Any]:
    """Delete a document and its vector embeddings."""
    success = ingestion_service.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Also clean up vector store
    chroma_store.delete_document_chunks(document_id)

    return {
        "success": True,
        "document_id": document_id
    }


@router.post("/directory")
def ingest_local_directory(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Batch-ingest all supported files (.md, .txt, .pdf) from a local directory path.
    """
    directory_path = body.get("directory_path", "").strip()
    if not directory_path:
        raise HTTPException(status_code=400, detail="directory_path is required")

    try:
        result = ingestion_service.ingest_directory(directory_path)
        return result
    except ValueError as val_err:
        raise HTTPException(status_code=404, detail=str(val_err))
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Directory ingestion failed: {str(err)}")
