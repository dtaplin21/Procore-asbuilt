"""Procore may embed the app. Other sites may not."""

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from api.procore_frame import ProcoreFrameAncestorsMiddleware, frame_ancestors_policy


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(ProcoreFrameAncestorsMiddleware)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/deny")
    def deny(response: Response):
        response.headers["X-Frame-Options"] = "DENY"
        return {"ok": True}

    return TestClient(app)


def test_frame_ancestors_lists_only_procore_origins():
    response = _client().get("/health")
    policy = response.headers["content-security-policy"]
    assert policy == frame_ancestors_policy()
    sources = policy.removeprefix("frame-ancestors ").split()
    assert "https://sandbox.procore.com" in sources
    assert "https://app.procore.com" in sources
    assert "*" not in sources
    assert all(source.startswith("https://") and "procore." in source for source in sources)
    assert "x-frame-options" not in response.headers


def test_x_frame_options_deny_is_removed():
    response = _client().get("/deny")
    assert "x-frame-options" not in response.headers
    assert response.headers["content-security-policy"].startswith("frame-ancestors ")
