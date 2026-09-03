import sys
import os
from pathlib import Path
import pytest

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

@pytest.fixture(autouse=True)
def configure_test_environment(monkeypatch):
    """Ensure fast, deterministic test runs by defaulting to mock LLM and hash embeddings."""
    from backend.app.config.settings import settings
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "hash")
