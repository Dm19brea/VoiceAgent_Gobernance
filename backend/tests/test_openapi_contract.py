"""M5.6 — the OpenAPI schema reflects the doc 4.4 read contract (spec S11)."""

from typing import Any

from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)

READ_PATHS = [
    "/sessions/{session_id}",
    "/sessions/{session_id}/events",
    "/sessions/{session_id}/evidences",
    "/sessions/{session_id}/report",
    "/agents/{agent_id}/sessions",
]


def _paths() -> dict[str, Any]:
    schema: dict[str, Any] = client.get("/openapi.json").json()
    paths: dict[str, Any] = schema["paths"]
    return paths


def test_openapi_exposes_every_read_path_with_get() -> None:
    paths = _paths()

    for path in READ_PATHS:
        assert path in paths, f"missing path: {path}"
        assert "get" in paths[path]


def test_openapi_documents_404_on_lookups() -> None:
    paths = _paths()

    assert "404" in paths["/sessions/{session_id}"]["get"]["responses"]
    assert "404" in paths["/sessions/{session_id}/report"]["get"]["responses"]
