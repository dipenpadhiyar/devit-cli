"""Tests for {{project_name}} API."""

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_root():
    r = client.get("/")
    assert r.status_code == 200


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
