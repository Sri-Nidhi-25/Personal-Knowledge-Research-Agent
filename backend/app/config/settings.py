from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # General App Config
    APP_NAME: str = "Personal Knowledge Research Agent"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent
    DATA_DIR: Path = Path("data")
    DOCUMENTS_DIR: Path = Path("data/documents")
    CHROMA_DIR: Path = Path("data/chroma")
    KNOWLEDGE_DIR: Path = Path("data/knowledge")
    DATABASE_URL: str = "sqlite:///data/database/app.db"

    # LLM Settings
    LLM_PROVIDER: Literal["mock", "openai", "groq", "gemini", "ollama"] = "ollama"
    LLM_MODEL: str = "llama3.2"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "http://localhost:11434/v1"
    LLM_TEMPERATURE: float = 0.2

    # Embeddings Settings
    EMBEDDING_PROVIDER: Literal["hash", "fastembed", "sentence-transformers", "openai", "ollama"] = "ollama"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIM: int = 768
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_LLM_MODEL: str = "llama3.2"

    # Search Settings
    SEARCH_PROVIDER: Literal["mock", "tavily", "duckduckgo", "brave"] = "brave"
    SEARCH_API_KEY: str = ""
    BRAVE_SEARCH_PROVIDER: Literal["mock", "brave"] = "mock"
    BRAVE_SEARCH_API_KEY: str = ""

    # Research Safety Budgets & Limits
    MAX_RESEARCH_ITERATIONS: int = 8
    MAX_SEARCH_QUERIES: int = 15
    MAX_SOURCES_PER_RUN: int = 25
    MAX_FETCHES_PER_RUN: int = 25
    MAX_RUNTIME_MINUTES: int = 10
    FETCH_TIMEOUT_SECONDS: int = 15
    MAX_CONTENT_LENGTH_BYTES: int = 1000000
    MAX_SEARCH_DEPTH: int = 3

    def ensure_directories(self) -> None:
        for path in [self.DATA_DIR, self.DOCUMENTS_DIR, self.CHROMA_DIR, self.KNOWLEDGE_DIR, Path("data/database")]:
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
