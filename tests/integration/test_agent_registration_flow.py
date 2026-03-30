"""Integration test: agent registration flow.

POST /kya/agents → GET /kya/agents/{id} → GET /trust/tier/{id}
Uses TestClient with Layer 1 app.
"""

from fastapi.testclient import TestClient

from src.layer1.app import app


class TestAgentRegistrationFlow:
    def test_health_check(self) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "layer1"

    def test_all_routers_mounted(self) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        # KYA routes exist (501 = not wired yet, not 404)
        assert client.post("/kya/agents", json={"agent_type": "test"}).status_code == 501
        assert client.get("/kya/agents/00000000-0000-0000-0000-000000000001").status_code == 501

        # Trust routes exist
        assert client.get("/trust/tier/00000000-0000-0000-0000-000000000001").status_code == 501

        # Behavioral routes exist
        assert client.get("/behavioral/score/00000000-0000-0000-0000-000000000001").status_code == 501

        # CircuitBreaker routes exist
        assert client.post("/circuit-breaker/activate").status_code == 501
