from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "lecturer-test-token"


def test_public_room_payload_is_what_the_lecturer_page_restores():
    client = TestClient(create_app(make_settings()))
    created = client.post(
        "/api/rooms",
        headers={"x-lecturer-token": TOKEN},
        json={"title": "Graphs"},
    ).json()
    fetched = client.get(f"/api/rooms/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == {"id": created["id"], "title": "Graphs"}
    missing = client.get("/api/rooms/missing")
    assert missing.status_code == 404
    assert missing.json()["error"] == "unknown_room"


def test_unlock_loads_saved_model_settings_without_a_reload():
    script = (ROOT / "app" / "static" / "lecturer.js").read_text(encoding="utf-8")
    handler = script.split('"#save-token"')[1].split("const ROOM_KEY")[0]
    assert "await loadLlm()" in handler
    assert 'document.querySelector("#provider").value = config.provider' in script
    assert 'document.querySelector("#model").value = config.model' in script
    assert 'document.querySelector("#base-url").value = config.base_url' in script


def test_lecturer_script_restores_the_saved_room_or_drops_it():
    script = (ROOT / "app" / "static" / "lecturer.js").read_text(encoding="utf-8")
    assert 'const ROOM_KEY = "zoomoodle-lecturer-room"' in script
    assert "sessionStorage.getItem(ROOM_KEY)" in script
    assert "sessionStorage.setItem(ROOM_KEY, room.id)" in script
    assert 'err.message === "unknown_room"' in script
    assert "restoreRoom()" in script
