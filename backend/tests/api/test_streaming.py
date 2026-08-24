"""Integration test for SSE research event streaming."""
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_sse_streaming_endpoint():
    # Start a research run to produce events
    res = client.post("/api/v1/research/start", json={"query": "What is reinforcement learning?"})
    assert res.status_code == 200
    run_id = res.json()["run_id"]

    # Connect to the stream endpoint
    with client.stream("GET", f"/api/v1/research/runs/{run_id}/stream") as stream_res:
        assert stream_res.status_code == 200
        assert "text/event-stream" in stream_res.headers.get("content-type", "")

        lines = []
        for line in stream_res.iter_lines():
            if line:
                lines.append(line)
            if len(lines) >= 6:
                break

        assert len(lines) > 0
        assert any("event:" in l or "data:" in l for l in lines)
