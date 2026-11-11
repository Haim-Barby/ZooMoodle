import json
import logging

from app.llm.providers import LLMResponse, ToolCall
from tests.conftest import HOME_IP, check_in_class, join, make_client, open_room, signed

SECRET_KEY = "sk-test-SECRET-never-store-0123456789"


def _students(app, client):
    room_id, headers = open_room(client)
    inside = check_in_class(app, client, room_id, "דנה לוי", zone="middle-center")
    remote = join(client, room_id, "יוסי כהן", "remote", ip=HOME_IP).json()
    return room_id, headers, inside, remote


def test_poll_note_and_question_from_the_phone_reach_the_dashboard():
    app, client = make_client()
    room_id, headers, inside, remote = _students(app, client)
    poll = client.post(f"/api/rooms/{room_id}/polls", json={"question": "מהו נוירון?", "options": ["תא", "שריר"], "correct_option": "תא"}, headers=headers).json()
    listed = signed(client, inside, "GET", f"/api/rooms/{room_id}/polls").json()["polls"][0]
    assert "counts" not in listed and "correct_option" not in listed
    vote = signed(client, inside, "POST", f"/api/rooms/{room_id}/polls/{poll['id']}/answers", {"option": "תא"})
    assert vote.json()["counts"] == {"תא": 1, "שריר": 0}
    assert signed(client, inside, "POST", f"/api/rooms/{room_id}/polls/{poll['id']}/answers", {"option": "תא"}).status_code == 409
    signed(client, remote, "POST", f"/api/rooms/{room_id}/polls/{poll['id']}/answers", {"option": "שריר"})
    signed(client, remote, "POST", f"/api/rooms/{room_id}/comments", {"text": "השקף לא ברור"})
    q1 = signed(client, inside, "POST", f"/api/rooms/{room_id}/questions", {"text": "מה זה סינפסה?"}).json()["id"]
    signed(client, remote, "POST", f"/api/rooms/{room_id}/questions", {"text": "יש מבחן?"})
    signed(client, remote, "POST", f"/api/rooms/{room_id}/questions/{q1}/upvote")
    dash = client.get(f"/api/rooms/{room_id}/dashboard", headers=headers).json()
    assert dash["polls"][0]["counts"] == {"תא": 1, "שריר": 1}
    assert dash["comments"][0]["text"] == "השקף לא ברור" and dash["comments"][0]["name"] == "יוסי כהן"
    assert [q["text"] for q in dash["questions"]] == ["מה זה סינפסה?", "יש מבחן?"]
    assert dash["questions"][0]["votes"] == 1
    client.post(f"/api/rooms/{room_id}/polls/{poll['id']}/close", headers=headers)
    assert signed(client, inside, "GET", f"/api/rooms/{room_id}/polls").json()["polls"][0]["open"] is False


def test_unsigned_or_pending_students_cannot_post():
    app, client = make_client()
    room_id, _headers = open_room(client)
    assert client.post(f"/api/rooms/{room_id}/comments", json={"text": "x"}).status_code == 401
    pending = join(client, room_id, "עמית שמש", "in_class").json()
    assert signed(client, pending, "POST", f"/api/rooms/{room_id}/comments", {"text": "x"}).status_code == 403


def test_lecturer_uploads_homework_and_students_view_it():
    app, client = make_client()
    room_id, headers, inside, remote = _students(app, client)
    data = "תרגיל 4: נוירון פרספטרון".encode("utf-8")
    assert client.post(f"/api/rooms/{room_id}/homework", files={"file": ("hw4.txt", data, "text/plain")}).status_code == 401
    up = client.post(f"/api/rooms/{room_id}/homework", data={"title": "תרגיל 4"}, files={"file": ("hw4.txt", data, "text/plain")}, headers=headers)
    assert up.status_code == 200
    hw_id = up.json()["id"]
    listed = signed(client, remote, "GET", f"/api/rooms/{room_id}/homework").json()["homework"]
    assert listed[0]["title"] == "תרגיל 4" and listed[0]["filename"] == "hw4.txt"
    got = signed(client, inside, "GET", f"/api/rooms/{room_id}/homework/{hw_id}")
    assert got.status_code == 200 and got.content == data
    assert got.headers["content-disposition"].startswith("attachment")
    assert got.headers["x-content-type-options"] == "nosniff"
    assert client.get(f"/api/rooms/{room_id}/homework/{hw_id}").status_code == 401


class FakeProvider:
    seen_keys = []

    def __init__(self, config):
        FakeProvider.seen_keys.append(config.api_key)
        self.calls = 0

    def complete(self, messages, tools, max_tokens=1200):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(text="", tool_calls=[ToolCall("1", "get_poll_results", {"poll_id": "all"})], model="fake")
        report = {
            "kind": "lesson_summary",
            "topics": ["נוירונים ופרספטרון"],
            "zone_findings": [],
            "recommendations": ["לחזור על סינפסות"],
            "missing_data": ["transcript"],
            "citations": [],
        }
        return LLMResponse(text="", tool_calls=[ToolCall("2", "produce_report", {"report": report})], model="fake")

    def test_connection(self):
        raise NotImplementedError


def _all_state_text(app) -> str:
    seen = []
    for room in app.state.store.rooms.values():
        seen.append(repr(vars(room)))
    seen.append(repr(vars(app.state.store)))
    seen.append(repr(vars(app.state.settings)))
    return "\n".join(seen)


def test_lecturer_summary_with_optional_key_is_published_and_key_not_kept(caplog, capsys):
    app, client = make_client()
    app.state.provider_factory = FakeProvider
    room_id, headers, inside, _remote = _students(app, client)
    assert signed(client, inside, "GET", f"/api/rooms/{room_id}/summary").json()["text"] == ""
    caplog.set_level(logging.DEBUG)
    made = client.post(
        f"/api/rooms/{room_id}/summary/generate",
        json={"provider": "openai", "model": "gpt-4o-mini", "api_key": SECRET_KEY},
        headers=headers,
    )
    assert made.status_code == 200, made.text
    assert made.json()["published"] is True and "לחזור על סינפסות" in made.json()["text"]
    assert FakeProvider.seen_keys[-1] == SECRET_KEY
    seen = signed(client, inside, "GET", f"/api/rooms/{room_id}/summary").json()
    assert "נוירונים ופרספטרון" in seen["text"]
    out = capsys.readouterr()
    assert SECRET_KEY not in caplog.text and SECRET_KEY not in out.out and SECRET_KEY not in out.err
    assert SECRET_KEY not in _all_state_text(app)
    assert SECRET_KEY not in made.text


def test_student_summary_is_private_and_needs_no_lecturer():
    app, client = make_client()
    app.state.provider_factory = FakeProvider
    room_id, headers, inside, _remote = _students(app, client)
    mine = signed(client, inside, "POST", f"/api/rooms/{room_id}/summary/generate", {"provider": "openai", "model": "m", "api_key": SECRET_KEY})
    assert mine.status_code == 200 and mine.json()["published"] is False
    assert client.get(f"/api/rooms/{room_id}/summary", headers=headers).json()["text"] == ""
    assert SECRET_KEY not in _all_state_text(app)
    missing = signed(client, inside, "POST", f"/api/rooms/{room_id}/summary/generate", {"provider": "openai", "model": "m"})
    assert missing.status_code == 400 and missing.json()["error"] == "missing_key"


def test_manual_summary_without_any_key():
    app, client = make_client()
    room_id, headers, inside, _remote = _students(app, client)
    client.post(f"/api/rooms/{room_id}/summary", json={"text": "סיכום ידני"}, headers=headers)
    assert signed(client, inside, "GET", f"/api/rooms/{room_id}/summary").json()["text"] == "סיכום ידני"


def test_emails_and_id_numbers_never_leave_the_server():
    app, client = make_client()
    room_id, headers, inside, remote = _students(app, client)
    check_in_class(app, client, room_id, "עמית שמש")
    check_in_class(app, client, room_id, "עמית שמש")
    texts = [
        client.get(f"/api/rooms/{room_id}/roster/names").text,
        client.get(f"/api/rooms/{room_id}").text,
        client.get(f"/api/rooms/{room_id}/dashboard", headers=headers).text,
        client.get(f"/api/rooms/{room_id}/export.csv", headers=headers).content.decode("utf-8"),
        signed(client, inside, "GET", f"/api/rooms/{room_id}/me").text,
        signed(client, remote, "GET", f"/api/rooms/{room_id}/me").text,
    ]
    xlsx = client.get(f"/api/rooms/{room_id}/export.xlsx", headers=headers).content
    for text in texts:
        for secret in ("@example.test", "dana@", "123456789", "987654321", "111122223"):
            assert secret not in text
    assert b"example.test" not in xlsx
    room = app.state.store.get(room_id)
    for entry in room.roster.entries.values():
        assert "example.test" not in repr(entry)
        assert "123456789" not in repr(vars(entry))
