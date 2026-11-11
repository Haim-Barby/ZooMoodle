from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings

ROOT = Path(__file__).resolve().parents[1]


def test_lecturer_and_student_pages_load():
    client = TestClient(create_app(make_settings()))
    lecturer = client.get("/")
    student = client.get("/student")
    assert lecturer.status_code == 200
    assert "Lecturer token" in lecturer.text
    assert "/static/lecturer.js" in lecturer.text
    assert student.status_code == 200
    assert 'id="check-result"' in student.text
    assert 'id="question-result"' in student.text
    assert "/static/student.js" in student.text
    assert client.get("/static/lecturer.js").status_code == 200
    assert client.get("/static/student.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_student_errors_are_sentences_and_statuses_are_separate():
    html = (ROOT / "app" / "static" / "student.html").read_text(encoding="utf-8")
    script = (ROOT / "app" / "static" / "student.js").read_text(encoding="utf-8")
    assert html.index('id="check-result"') < html.index('id="question-result"')
    assert "function explain(" in script
    for code in ("unknown_room", "bad_token", "missing_question", "already_answered", "already_upvoted"):
        assert code + ":" in script
    question = script.split('"#send-question"')[1].split("async function refreshLesson")[0]
    assert "setQuestionResult(" in question
    assert "setResult(" not in question
    checkin = script.split("async function checkIn")[1].split('"#typed"')[0]
    assert "explain(" in checkin
    assert "body.error ||" not in checkin


def test_student_id_is_optional_and_the_mic_stops_after_check_in():
    html = (ROOT / "app" / "static" / "student.html").read_text(encoding="utf-8")
    script = (ROOT / "app" / "static" / "student.js").read_text(encoding="utf-8")
    assert "Student id (optional)" in html
    assert 'id="mode-status"' in html
    checkin = script.split("async function checkIn")[1].split('"#typed"')[0]
    assert "!who.studentId" not in checkin
    assert "stopListening()" in checkin
    assert 'if (flow.step === "lesson") return;' in script
    stop = script.split("function stopListening")[1].split('"#stop"')[0]
    assert "getTracks().forEach((track) => track.stop())" in stop
    assert "onaudioprocess = null" in stop
    remote = script.split('"#remote"')[1].split('"#listen"')[0]
    assert "#mode-status" in remote and "#join-status" not in remote


def test_check_in_uses_a_three_by_three_map_and_the_lesson_has_no_zone_picker():
    html = (ROOT / "app" / "static" / "student.html").read_text(encoding="utf-8")
    script = (ROOT / "app" / "static" / "student.js").read_text(encoding="utf-8")
    assert "Lecturer / board" in html
    assert 'id="lesson-zones"' not in html
    assert 'id="count-in-class"' in html
    assert 'id="count-remote"' in html
    assert 'id="lesson-summary"' in html
    assert 'id="lesson-title"' in html
    for zone in ("front-center", "middle-center", "back-center"):
        assert zone in script
    assert "No polls yet" in html
    assert "Summary not published yet" in script
    assert "/counts" in script
    assert "/questions" in script
    assert "/summary" in script
    assert "x-zoomoodle-signature" in script
    assert "zoomoodle-session" in script
    assert "session_revoked" in script
    assert "HKDF" in script
    assert "holder.appendChild" not in script
    remote = script.split('"#remote"')[1].split('"#listen"')[0]
    assert "seat" not in remote

def test_student_page_vendors_jsqr_and_has_the_rotating_scanner():
    client = TestClient(create_app(make_settings()))
    student = client.get("/student")
    assert "/static/jsqr.js" in student.text
    assert 'id="scan-screen-qr"' in student.text
    assert 'id="screen-qr-scanner"' in student.text
    assert 'id="email"' in student.text
    assert 'id="pin"' not in student.text
    assert "4 ספרות" not in student.text
    assert "ארבע הספרות" not in student.text
    assert client.get("/static/jsqr.js").status_code == 200
    script = (ROOT / "app" / "static" / "student.js").read_text(encoding="utf-8")
    assert "jsQR(" in script
    assert "presence/screen-qr" in script
    lecturer = (ROOT / "app" / "static" / "lecturer.html").read_text(encoding="utf-8")
    assert 'id="screen-qr"' in lecturer
    assert 'id="screen-qr-flicker"' in lecturer
    assert "ברקוד רץ" in lecturer
    assert "שתי שניות" in (ROOT / "app" / "static" / "student.html").read_text(encoding="utf-8")
    assert "qr_static" in script
    assert "holdSeconds" in script
