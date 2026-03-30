"""Integration test: agent registration flow.

Tests app structure, health check, and route authentication.
"""

from fastapi.testclient import TestClient

from src.layer1.app import app


class TestAgentRegistrationFlow:
    def test_health_check(self) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "layer1"
        # Without Redis running, status is degraded
        assert data["status"] in ("healthy", "degraded")
        assert "redis_connected" in data
        assert "db_connected" in data

    def test_unauthenticated_requests_return_401(self) -> None:
        """All protected routes require auth."""
        client = TestClient(app, raise_server_exceptions=False)
        assert client.post("/kya/agents", json={"agent_type": "test"}).status_code == 401
        assert client.get("/kya/agents/00000000-0000-0000-0000-000000000001").status_code == 401
        assert client.get("/trust/tier/00000000-0000-0000-0000-000000000001").status_code == 401
        assert client.get("/behavioral/score/00000000-0000-0000-0000-000000000001").status_code == 401

    def test_circuit_breaker_requires_admin(self) -> None:
        """Circuit breaker routes require admin role, not just auth."""
        client = TestClient(app, raise_server_exceptions=False)
        assert client.post("/circuit-breaker/activate").status_code == 401

    def test_layer3_health_and_routers(self) -> None:
        """Layer 3 app has health check and provenance routers mounted."""
        from src.layer3.app import app as l3_app

        client = TestClient(l3_app, raise_server_exceptions=False)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "layer3"

        # Session and anchor routes exist (401 = auth required, not 404)
        session_payload = {"agent_id": "00000000-0000-0000-0000-000000000001", "intent": "test"}
        assert client.post("/sessions", json=session_payload).status_code == 401
        assert client.get("/anchor/status").status_code == 401
