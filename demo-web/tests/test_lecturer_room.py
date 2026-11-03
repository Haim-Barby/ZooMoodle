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
    assert fetched.json() == {
        "id": created["id"],
        "title": "Graphs",
        "closed": False,
        "audio_band": "ultrasonic",
        "proof": "both",
        "student_path": f"/student?room={created['id']}",
        "student_url": f"http://testserver/student?room={created['id']}",
    }
    assert created["student_url"] == fetched.json()["student_url"]
    missing = client.get("/api/rooms/missing")
    assert missing.status_code == 404
    assert missing.json()["error"] == "unknown_room"


def test_student_url_prefers_the_render_public_origin(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://zoomoodle-demo.onrender.com/")
    client = TestClient(create_app(make_settings()))
    created = client.post(
        "/api/rooms",
        headers={"x-lecturer-token": TOKEN},
        json={"title": "Graphs"},
    ).json()
    assert created["student_path"] == f"/student?room={created['id']}"
    assert created["student_url"] == f"https://zoomoodle-demo.onrender.com/student?room={created['id']}"
    monkeypatch.setenv("ZOOMODLE_PUBLIC_ORIGIN", "https://class.example:8443")
    again = client.post(
        "/api/rooms",
        headers={"x-lecturer-token": TOKEN},
        json={"title": "Graphs"},
    ).json()
    assert again["student_url"] == f"https://class.example:8443/student?room={again['id']}"
    monkeypatch.setenv("ZOOMODLE_PUBLIC_ORIGIN", "javascript:alert(1)")
    ignored = client.post(
        "/api/rooms",
        headers={"x-lecturer-token": TOKEN},
        json={"title": "Graphs"},
    ).json()
    assert ignored["student_url"].startswith("https://zoomoodle-demo.onrender.com/student?room=")


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
    assert "room.student_url || room.student_path" in script
    assert 'err.message === "unknown_room"' in script
    assert "restoreRoom()" in script


def test_attendance_note_names_the_room_band_and_open_rooms_can_be_reopened():
    html = (ROOT / "app" / "static" / "lecturer.html").read_text(encoding="utf-8")
    script = (ROOT / "app" / "static" / "lecturer.js").read_text(encoding="utf-8")
    assert "used the ultrasonic one-time code" not in html
    assert 'id="attendance-band-note"' in html
    assert 'id="open-rooms"' in html
    assert "function updateBandNote" in script
    assert 'api("/api/rooms")' in script


def test_lecturer_reads_questions_by_votes_and_can_publish_a_summary():
    html = (ROOT / "app" / "static" / "lecturer.html").read_text(encoding="utf-8")
    script = (ROOT / "app" / "static" / "lecturer.js").read_text(encoding="utf-8")
    assert 'id="class-map"' in html
    assert "Lecturer / board" in html
    assert "open the join page" in html
    assert 'id="question-list"' in html
    assert 'id="summary-draft"' in html
    assert 'id="publish-summary"' in html
    assert "Students are not named" in html
    overview = html.split('data-panel="overview"')[1].split('data-panel="attendance"')[0]
    assert 'id="class-map"' in overview
    assert 'id="question-list"' in overview
    assert 'id="polls"' in overview
    assert 'id="summary-draft"' in overview
    questions = script.split('"#question-list"')[1].split('"#polls"')[0]
    assert "item.votes" in questions
    assert "student_id" not in questions
    assert "function renderClassMap" in script
    assert "Verified" in script
    assert "/summary/publish" in script
    assert "front-center" in script
    assert "ZooQR.toSvg(link" in script
