import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "lecturer-test-token"


def _client():
    application = create_app(make_settings())
    return application, TestClient(application)


def test_overview_fingerprint_is_not_the_room_secret():
    application, client = _client()
    headers = {"x-lecturer-token": TOKEN}
    first = client.post("/api/rooms", headers=headers, json={"title": "One"}).json()
    second = client.post("/api/rooms", headers=headers, json={"title": "Two"}).json()
    denied = client.get(f"/api/rooms/{first['id']}/overview")
    assert denied.status_code == 401
    overview = client.get(f"/api/rooms/{first['id']}/overview", headers=headers)
    assert overview.status_code == 200
    body = overview.json()
    assert body["closed"] is False
    assert len(body["key_fingerprint"]) == 12
    assert len(body["salt_fingerprint"]) == 12
    assert body["key_fingerprint"] != body["salt_fingerprint"]
    assert body["counts"] == {"in_class": 0, "remote": 0, "flagged": 0}
    assert body["token"]["code"]
    assert body["token"]["seconds_left"] >= 0
    other = client.get(f"/api/rooms/{second['id']}/overview", headers=headers).json()
    assert other["key_fingerprint"] != body["key_fingerprint"]
    room = application.state.store.get(first["id"])
    encoded = json.dumps(body)
    assert room.salt.hex() not in encoded
    assert room.key.hex() not in encoded
    assert "lecturer-test-token" not in encoded
    assert "test-master-secret" not in encoded


def test_closed_room_rejects_new_checkins_and_still_exports():
    _application, client = _client()
    headers = {"x-lecturer-token": TOKEN}
    room = client.post("/api/rooms", headers=headers, json={"title": "Lesson"}).json()
    closed = client.post(f"/api/rooms/{room['id']}/close", headers=headers)
    assert closed.status_code == 200
    assert closed.json()["closed"] is True
    rejected = client.post(
        f"/api/rooms/{room['id']}/challenge",
        json={"student_id": "stu-1", "device_id": "abcd", "public_jwk": {}},
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"] == "room_closed"
    exported = client.get(f"/api/rooms/{room['id']}/export.csv", headers=headers)
    assert exported.status_code == 200


def test_favicon_is_served():
    _application, client = _client()
    icon = client.get("/favicon.ico")
    assert icon.status_code == 200
    assert icon.content[:4] == b"\x00\x00\x01\x00"


def test_diagram_catalog_lists_every_svg_without_rewriting_it():
    _application, client = _client()
    listed = client.get("/api/diagrams")
    assert listed.status_code == 200
    diagrams = listed.json()["diagrams"]
    files = {item["file"] for item in diagrams}
    on_disk = {path.name for path in (ROOT / "docs" / "diagrams").glob("*.svg")}
    assert files == on_disk
    assert "classes.svg" in files
    sample = client.get("/diagrams/classes.svg")
    assert sample.status_code == 200
    assert sample.content.startswith(b"<svg") or b"<svg" in sample.content[:200]
    original = (ROOT / "docs" / "diagrams" / "classes.svg").read_bytes()
    assert sample.content == original
