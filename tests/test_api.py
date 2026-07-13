from fastapi.testclient import TestClient

from app.api import app


client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ask_high_risk():
    response = client.post("/ask", json={"question": "超过退换货期限能特殊退款吗？", "user_id": 1, "store_id": "S001"})
    assert response.status_code == 200
    body = response.json()
    assert body["need_manager_confirmation"] is True
    assert body["query_id"] is not None


def test_management_api_is_role_protected():
    assert client.get("/reviews").status_code == 403
    assert client.get("/reviews", headers={"X-User-Id": "2"}).status_code == 200
    assert client.get("/reviews", headers={"X-User-Id": "3"}).status_code == 200


def test_manager_cannot_access_audit_logs():
    assert client.get("/audit-logs", headers={"X-User-Id": "2"}).status_code == 403
    assert client.get("/audit-logs", headers={"X-User-Id": "3"}).status_code == 200


def test_dashboard_is_scoped_and_protected():
    assert client.get("/dashboard").status_code == 403
    response = client.get("/dashboard", headers={"X-User-Id": "2"})
    assert response.status_code == 200
    assert "associate_active_rate" in response.json()


def test_catalog_write_requires_regional_role():
    products = client.get("/catalog/products").json()
    assert products
    manager = client.put("/catalog/products", headers={"X-User-Id": "2"}, json={"products": products})
    assert manager.status_code == 403


def test_product_request_list_is_role_scoped():
    assert client.get("/product-requests").status_code == 403
    assert client.get("/product-requests", headers={"X-User-Id": "2"}).status_code == 200
    assert client.get("/product-requests", headers={"X-User-Id": "3"}).status_code == 200
