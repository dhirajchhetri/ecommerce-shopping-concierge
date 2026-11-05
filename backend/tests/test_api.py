from fastapi.testclient import TestClient

from kitline.api import create_app
from kitline.config import Settings
from kitline.vectorstore import PG_SEARCH_SQL, index_mapping, knn_body, vector_literal


def _client() -> TestClient:
    settings = Settings(mode="offline", session_store="memory", vector_store="local", embeddings="local")
    return TestClient(create_app(settings))


def test_health_and_catalog():
    client = _client()
    health = client.get("/api/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["mode"] == "offline"
    assert body["model"] == "stub"
    assert body["catalog_size"] >= 12

    catalog = client.get("/api/catalog")
    assert catalog.status_code == 200
    skus = {item["sku"] for item in catalog.json()}
    assert "NS-PRO-16" in skus
    assert "HB-DOCK-A" in skus


def test_message_returns_a_checked_package():
    client = _client()
    created = client.post("/api/sessions")
    assert created.status_code == 200
    session_id = created.json()["session_id"]
    response = client.post(
        f"/api/sessions/{session_id}/messages",
        json={
            "message": "I need a laptop for video editing, a monitor, and a two-year warranty.",
            "budget_cents": 250_000,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "validated"
    assert body["package"]["grand_total_cents"] <= 250_000
    assert all(check["ok"] for check in body["package"]["checks"])

    missing = client.post("/api/sessions/ses_doesnotexist/messages", json={"message": "A laptop"})
    assert missing.status_code == 404

    empty = client.post(f"/api/sessions/{session_id}/messages", json={"message": ""})
    assert empty.status_code == 422


def test_vector_query_shapes():
    literal = vector_literal([0.25, -0.5])
    assert literal.startswith("[") and "0.25000000" in literal
    assert "<=>" in PG_SEARCH_SQL
    body = knn_body([0.1, 0.2], 4)
    assert body["size"] == 4
    assert body["query"]["knn"]["embedding"]["k"] == 4
    mapping = index_mapping(256)
    assert mapping["mappings"]["properties"]["embedding"]["dimension"] == 256
