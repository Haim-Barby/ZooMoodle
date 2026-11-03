"""Live lesson screen: headcounts, poll results, questions, and a published summary."""

import base64

from fastapi.testclient import TestClient

from app.domain import SEAT_ZONES
from app.main import create_app
from tests.conftest import make_device, make_settings, signed_request

TOKEN = "lecturer-test-token"


def _client():
    return TestClient(create_app(make_settings()))


def _room(client, title="Graphs"):
    created = client.post(
        "/api/rooms",
        headers={"x-lecturer-token": TOKEN},
        json={"title": title},
    ).json()
    return created["id"]


def _check_in(client, room_id, zone="front-center", student_id=""):
    code = client.get(f"/api/rooms/{room_id}/token", headers={"x-lecturer-token": TOKEN}).json()["code"]
    device = make_device()
    opened = client.post(
        f"/api/rooms/{room_id}/challenge",
        json={"student_id": student_id, "device_id": device["device_id"], "public_jwk": device["jwk"]},
    )
    assert opened.status_code == 200
    opened = opened.json()
    signature = base64.b64encode(device["sign"](opened["challenge_id"], opened["nonce"])).decode()
    checked = client.post(
        f"/api/rooms/{room_id}/checkin",
        json={
            "challenge_id": opened["challenge_id"],
            "signature": signature,
            "mode": "in_class",
            "token_code": code,
            "seat_zone": zone,
            "student_name": "",
        },
    )
    assert checked.status_code == 200
    return checked.json()


def _remote(client, room_id):
    body = client.post(f"/api/rooms/{room_id}/remote-join").json()
    return {
        "session_id": body["session_id"],
        "session_key": body["session_key"],
        "student_id": body["marker"],
    }


def test_seat_map_is_three_by_three_and_center_checks_in():
    assert SEAT_ZONES == (
        "front-left",
        "front-center",
        "front-right",
        "middle-left",
        "middle-center",
        "middle-right",
        "back-left",
        "back-center",
        "back-right",
    )
    client = _client()
    room_id = _room(client)
    body = _check_in(client, room_id, "middle-center")
    assert body["seat_zone"] == "middle-center"
    assert len(body["attendance_id"]) >= 8


def test_counts_are_public_headcounts_without_secrets():
    client = _client()
    room_id = _room(client, "Evening lab")
    checked = _check_in(client, room_id, "front-left", student_id="stu-secret-name")
    remote = client.post(f"/api/rooms/{room_id}/remote-join")
    assert remote.status_code == 200
    assert client.get(f"/api/rooms/{room_id}/counts").status_code == 401
    listed = signed_request(client, checked, "GET", f"/api/rooms/{room_id}/counts")
    assert listed.status_code == 200
    assert listed.json() == {
        "title": "Evening lab",
        "closed": False,
        "in_class": 1,
        "remote": 1,
    }
    text = listed.text
    assert checked["attendance_id"] not in text
    assert checked["session_key"] not in text
    assert "stu-secret-name" not in text
    assert "flagged" not in text
    assert "token" not in text
    assert TOKEN not in text
    missing = client.get("/api/rooms/missing/counts")
    assert missing.status_code == 404


def test_poll_results_appear_only_after_that_student_votes():
    client = _client()
    room_id = _room(client)
    poll = client.post(
        f"/api/rooms/{room_id}/polls",
        headers={"x-lecturer-token": TOKEN},
        json={"question": "Pick one", "options": ["Yes", "No"], "correct_option": "Yes"},
    ).json()
    alice = _remote(client, room_id)
    bob = _remote(client, room_id)
    cara = _remote(client, room_id)
    hidden = signed_request(client, alice, "GET", f"/api/rooms/{room_id}/polls").json()["polls"][0]
    assert "counts" not in hidden
    assert "correct_option" not in hidden
    assert "voted_option" not in hidden
    assert client.get(f"/api/rooms/{room_id}/polls").status_code == 401

    first = signed_request(
        client,
        alice,
        "POST",
        f"/api/rooms/{room_id}/polls/{poll['id']}/answers",
        {"student_id": alice["student_id"], "option": "Yes", "seat_zone": "remote"},
    )
    assert first.status_code == 200
    assert first.json()["counts"] == {"Yes": 1, "No": 0}
    assert first.json()["voted_option"] == "Yes"
    assert alice["student_id"] not in first.text
    assert alice["session_key"] not in first.text

    still_hidden = signed_request(client, bob, "GET", f"/api/rooms/{room_id}/polls").json()["polls"][0]
    assert "counts" not in still_hidden
    mine = signed_request(client, alice, "GET", f"/api/rooms/{room_id}/polls").json()["polls"][0]
    assert mine["counts"] == {"Yes": 1, "No": 0}
    assert mine["voted_option"] == "Yes"
    assert "correct_option" not in mine
    assert alice["student_id"] not in signed_request(client, alice, "GET", f"/api/rooms/{room_id}/polls").text

    other = signed_request(client, bob, "GET", f"/api/rooms/{room_id}/polls").json()["polls"][0]
    assert "counts" not in other
    remote = signed_request(
        client,
        bob,
        "POST",
        f"/api/rooms/{room_id}/polls/{poll['id']}/answers",
        {"student_id": bob["student_id"], "option": "No", "seat_zone": "remote"},
    )
    assert remote.status_code == 200
    assert remote.json()["counts"] == {"Yes": 1, "No": 1}
    blank = signed_request(
        client,
        cara,
        "POST",
        f"/api/rooms/{room_id}/polls/{poll['id']}/answers",
        {"student_id": cara["student_id"], "option": "Yes", "seat_zone": ""},
    )
    assert blank.status_code == 400
    assert blank.json()["error"] == "bad_zone"


def test_questions_are_anonymous_and_one_upvote_each():
    client = _client()
    room_id = _room(client)
    alice = _remote(client, room_id)
    bob = _remote(client, room_id)
    asked = signed_request(
        client,
        alice,
        "POST",
        f"/api/rooms/{room_id}/questions",
        {"student_id": alice["student_id"], "text": "Can you repeat the definition?"},
    )
    assert asked.status_code == 200
    question_id = asked.json()["id"]
    later = signed_request(
        client,
        bob,
        "POST",
        f"/api/rooms/{room_id}/questions",
        {"student_id": bob["student_id"], "text": "Is the homework due Friday?"},
    )
    assert later.status_code == 200
    later_id = later.json()["id"]

    empty = signed_request(
        client,
        alice,
        "POST",
        f"/api/rooms/{room_id}/questions",
        {"student_id": alice["student_id"], "text": "  "},
    )
    assert empty.status_code == 400
    assert empty.json()["error"] == "missing_question"

    own = signed_request(
        client,
        alice,
        "POST",
        f"/api/rooms/{room_id}/questions/{question_id}/upvote",
        {"student_id": alice["student_id"]},
    )
    assert own.status_code == 200
    assert own.json()["votes"] == 1
    again = signed_request(
        client,
        alice,
        "POST",
        f"/api/rooms/{room_id}/questions/{question_id}/upvote",
        {"student_id": alice["student_id"]},
    )
    assert again.status_code == 400
    assert again.json()["error"] == "already_upvoted"

    seen = signed_request(client, bob, "GET", f"/api/rooms/{room_id}/questions")
    assert seen.status_code == 200
    body = seen.json()["questions"]
    assert [item["id"] for item in body] == [question_id, later_id]
    assert body[0]["votes"] == 1
    assert body[0]["upvoted"] is False
    assert body[0]["text"] == "Can you repeat the definition?"
    assert alice["student_id"] not in seen.text
    assert alice["session_key"] not in seen.text
    assert "student_id" not in seen.text
    boosted = signed_request(
        client,
        bob,
        "POST",
        f"/api/rooms/{room_id}/questions/{later_id}/upvote",
        {"student_id": bob["student_id"]},
    )
    assert boosted.status_code == 200
    ordered = signed_request(client, alice, "GET", f"/api/rooms/{room_id}/questions").json()["questions"]
    assert [item["id"] for item in ordered] == [question_id, later_id]
    signed_request(
        client,
        alice,
        "POST",
        f"/api/rooms/{room_id}/questions/{later_id}/upvote",
        {"student_id": alice["student_id"]},
    )
    ordered = signed_request(client, bob, "GET", f"/api/rooms/{room_id}/questions").json()["questions"]
    assert ordered[0]["id"] == later_id
    assert ordered[0]["votes"] == 2
    assert ordered[0]["upvoted"] is True

    client.post(f"/api/rooms/{room_id}/close", headers={"x-lecturer-token": TOKEN})
    closed = signed_request(
        client,
        alice,
        "POST",
        f"/api/rooms/{room_id}/questions",
        {"student_id": alice["student_id"], "text": "Too late?"},
    )
    assert closed.status_code == 401
    assert closed.json()["error"] == "session_revoked"
    still = signed_request(client, bob, "GET", f"/api/rooms/{room_id}/questions")
    assert still.status_code == 200
    assert len(still.json()["questions"]) == 2


def test_summary_stays_hidden_until_the_room_is_closed_and_published():
    client = _client()
    room_id = _room(client)
    draft = client.post(
        f"/api/rooms/{room_id}/summary",
        headers={"x-lecturer-token": TOKEN},
        json={"text": "Draft only: HMAC means integrity."},
    )
    assert draft.status_code == 200
    assert draft.json()["published"] is False
    refused = client.post(f"/api/rooms/{room_id}/summary", json={"text": "nope"})
    assert refused.status_code == 401
    student_creds = _remote(client, room_id)
    assert client.get(f"/api/rooms/{room_id}/summary").status_code == 401

    student = signed_request(client, student_creds, "GET", f"/api/rooms/{room_id}/summary")
    assert student.json() == {"closed": False, "published": False, "text": ""}
    assert "Draft only" not in student.text
    assert "draft" not in student.json()

    empty = client.post(
        f"/api/rooms/{room_id}/summary/publish",
        headers={"x-lecturer-token": TOKEN},
        json={"text": "   "},
    )
    assert empty.status_code == 400
    assert empty.json()["error"] == "missing_summary"

    published = client.post(
        f"/api/rooms/{room_id}/summary/publish",
        headers={"x-lecturer-token": TOKEN},
        json={"text": "HMAC is the integrity story. Revisit the definition."},
    )
    assert published.status_code == 200
    early = signed_request(client, student_creds, "GET", f"/api/rooms/{room_id}/summary")
    assert early.json()["published"] is True
    assert early.json()["text"] == ""
    assert "HMAC is the integrity story" not in early.text
    lecturer = client.get(f"/api/rooms/{room_id}/summary", headers={"x-lecturer-token": TOKEN}).json()
    assert lecturer["draft"] == "HMAC is the integrity story. Revisit the definition."
    assert "api_key" not in lecturer

    client.post(f"/api/rooms/{room_id}/close", headers={"x-lecturer-token": TOKEN})
    visible = signed_request(client, student_creds, "GET", f"/api/rooms/{room_id}/summary")
    assert visible.json()["closed"] is True
    assert visible.json()["text"] == "HMAC is the integrity story. Revisit the definition."
    assert "draft" not in visible.json()


def test_summary_can_be_written_without_an_llm_key():
    client = _client()
    room_id = _room(client)
    agent = client.post(f"/api/rooms/{room_id}/agent/summary", headers={"x-lecturer-token": TOKEN}, json={})
    assert agent.status_code == 503
    published = client.post(
        f"/api/rooms/{room_id}/summary/publish",
        headers={"x-lecturer-token": TOKEN},
        json={"text": "Written by hand because no model key is set."},
    )
    assert published.status_code == 200
    reader = _remote(client, room_id)
    client.post(f"/api/rooms/{room_id}/close", headers={"x-lecturer-token": TOKEN})
    visible = signed_request(client, reader, "GET", f"/api/rooms/{room_id}/summary")
    assert visible.json()["text"].startswith("Written by hand")
    assert reader["session_key"] not in visible.text
