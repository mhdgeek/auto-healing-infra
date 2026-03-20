"""
Unit tests — run with: pytest tests/ -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../app"))

import pytest
from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


class TestIndex:
    def test_returns_200(self, client):
        assert client.get("/").status_code == 200

    def test_returns_json(self, client):
        data = client.get("/").get_json()
        assert data["service"] == "auto-healing-demo"
        assert data["status"] == "running"

    def test_has_timestamp(self, client):
        data = client.get("/").get_json()
        assert data["timestamp"].endswith("Z")


class TestHealth:
    def test_returns_200(self, client):
        assert client.get("/health").status_code == 200

    def test_status_healthy(self, client):
        assert client.get("/health").get_json()["status"] == "healthy"


class TestReady:
    def test_returns_200(self, client):
        assert client.get("/ready").status_code == 200

    def test_status_ready(self, client):
        assert client.get("/ready").get_json()["status"] == "ready"


class TestMetrics:
    def test_returns_200(self, client):
        assert client.get("/metrics").status_code == 200

    def test_content_type_prometheus(self, client):
        assert "text/plain" in client.get("/metrics").content_type

    def test_contains_custom_metrics(self, client):
        client.get("/health")
        client.get("/")
        body = client.get("/metrics").data.decode()
        assert "app_requests_total" in body
        assert "app_request_latency_seconds" in body
        assert "app_info" in body


class TestWork:
    def test_returns_200(self, client):
        assert client.get("/work").status_code == 200

    def test_has_duration(self, client):
        data = client.get("/work").get_json()
        assert "duration_ms" in data
        assert data["duration_ms"] > 0


class TestChaos:
    def test_latency_mode_returns_200(self, client):
        res = client.get("/chaos?mode=latency")
        assert res.status_code == 200
        assert res.get_json()["chaos"] == "latency"

    def test_error_mode_returns_500(self, client):
        res = client.get("/chaos?mode=error")
        assert res.status_code == 500
        assert res.get_json()["chaos"] == "error"

    def test_random_mode_valid_status(self, client):
        assert client.get("/chaos?mode=random").status_code in [200, 500]

    def test_default_is_random(self, client):
        assert client.get("/chaos").status_code in [200, 500]

    def test_post_method_works(self, client):
        assert client.post("/chaos?mode=error").status_code == 500


class TestErrorHandlers:
    def test_404_returns_json(self, client):
        res = client.get("/does-not-exist")
        assert res.status_code == 404
        assert "error" in res.get_json()

    def test_metrics_count_requests(self, client):
        client.get("/health")
        client.get("/ready")
        body = client.get("/metrics").data.decode()
        assert "app_requests_total{" in body
