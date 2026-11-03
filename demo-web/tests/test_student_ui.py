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
    assert 'id="comment-result"' in student.text
    assert "/static/student.js" in student.text
    assert client.get("/static/lecturer.js").status_code == 200
    assert client.get("/static/student.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_student_errors_are_sentences_and_statuses_are_separate():
    html = (ROOT / "app" / "static" / "student.html").read_text(encoding="utf-8")
    script = (ROOT / "app" / "static" / "student.js").read_text(encoding="utf-8")
    assert html.index('id="check-result"') < html.index('id="comment-result"')
    assert "function explain(" in script
    for code in ("unknown_room", "bad_token", "missing_comment", "already_answered"):
        assert code + ":" in script
    comment = script.split('"#send-comment"')[1].split('"#send-homework"')[0]
    assert "setCommentResult(" in comment
    assert "setResult(" not in comment
    checkin = script.split("async function checkIn")[1].split('"#typed"')[0]
    assert "explain(" in checkin
    assert "body.error ||" not in checkin
