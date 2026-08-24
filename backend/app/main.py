"""FastAPI Main Application Entrypoint."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config.settings import settings
from backend.app.storage.sqlite_db import init_db
from backend.app.api.routes_health import router as health_router
from backend.app.api.routes_documents import router as documents_router
from backend.app.api.routes_knowledge import router as knowledge_router
from backend.app.api.routes_graph import router as graph_router
from backend.app.api.routes_research import router as research_router
from backend.app.api.routes_evaluation import router as evaluation_router

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database tables...")
    init_db()
    logger.info("Application startup complete.")
    yield
    logger.info("Application shutting down.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Personal Knowledge Research Agent API",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(health_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(graph_router, prefix="/api/v1")
app.include_router(research_router, prefix="/api/v1")
app.include_router(evaluation_router, prefix="/api/v1")


@app.get("/api/v1")
def api_root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/v1/health"
    }


# Mount Frontend SPA if available with content negotiation on root
from pathlib import Path
from fastapi import Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

frontend_dist = Path("frontend/dist")
if frontend_dist.exists() and (frontend_dist / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="static_assets")


@app.get("/")
def root(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept and frontend_dist.exists() and (frontend_dist / "index.html").exists():
        return FileResponse(frontend_dist / "index.html")
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/v1/health"
    }


@app.get("/app/{full_path:path}")
def serve_frontend_app(full_path: str):
    file_path = frontend_dist / full_path
    if file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(frontend_dist / "index.html")
