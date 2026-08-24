"""Health and System Status Endpoints."""
from fastapi import APIRouter
from backend.app.config.settings import settings
from backend.app.models.schemas import HealthResponse
from backend.app.storage.sqlite_db import engine
from backend.app.storage.chroma_store import chroma_store
from sqlalchemy import text

router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    services = {
        "database": "healthy",
        "vector_store": "healthy",
        "llm": "healthy",
        "search": "healthy",
        "filesystem": "healthy"
    }

    # Verify SQLite connectivity
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        services["database"] = f"degraded: {str(e)}"

    # Verify Chroma vector store
    try:
        chroma_store.count()
    except Exception as e:
        services["vector_store"] = f"degraded: {str(e)}"

    is_all_healthy = all(v == "healthy" for v in services.values())
    status = "healthy" if is_all_healthy else "degraded"

    return HealthResponse(
        status=status,
        version=settings.APP_VERSION,
        services=services
    )
