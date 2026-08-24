"""Unit tests for the Unified LLM Client."""
import pytest
from backend.app.agent.llm_client import LLMClient


def test_mock_llm_generate_text():
    client = LLMClient()
    resp = client.generate_text("Explain transformer architecture")
    assert len(resp) > 0
    assert isinstance(resp, str)


def test_mock_llm_generate_json_plan():
    client = LLMClient()
    data = client.generate_json("Create a research plan for Graph Neural Networks")
    assert isinstance(data, dict)
    assert "questions" in data
    assert "search_queries" in data
    assert len(data["questions"]) >= 1


def test_mock_llm_generate_json_verify():
    client = LLMClient()
    data = client.generate_json("Verify the following claim against evidence")
    assert isinstance(data, dict)
    assert "verification_status" in data
    assert "confidence" in data
