"""Live lesson screen: headcounts, poll results, questions, and a published summary."""

import base64

from fastapi.testclient import TestClient

from app.domain import SEAT_ZONES
from app.main import create_app
from tests.conftest import make_device, make_settings

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
    listed = client.get(f"/api/rooms/{room_id}/counts")
    assert listed.status_code == 200
    assert listed.json() == {
        "title": "Evening lab",
        "closed": False,
        "in_class": 1,
        "remote": 1,
    }
    text = listed.text
    assert checked["attendance_id"] not in text
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
    hidden = client.get(f"/api/rooms/{room_id}/polls").json()["polls"][0]
    assert "counts" not in hidden
    assert "correct_option" not in hidden
    assert "voted_option" not in hidden

    first = client.post(
        f"/api/rooms/{room_id}/polls/{poll['id']}/answers",
        json={"student_id": "phone-a", "option": "Yes", "seat_zone": "front-center"},
    )
    assert first.status_code == 200
    assert first.json()["counts"] == {"Yes": 1, "No": 0}
    assert first.json()["voted_option"] == "Yes"
    assert "phone-a" not in first.text

    still_hidden = client.get(f"/api/rooms/{room_id}/polls").json()["polls"][0]
    assert "counts" not in still_hidden
    mine = client.get(f"/api/rooms/{room_id}/polls", params={"student_id": "phone-a"}).json()["polls"][0]
    assert mine["counts"] == {"Yes": 1, "No": 0}
    assert mine["voted_option"] == "Yes"
    assert "correct_option" not in mine
    assert "phone-a" not in client.get(f"/api/rooms/{room_id}/polls", params={"student_id": "phone-a"}).text

    other = client.get(f"/api/rooms/{room_id}/polls", params={"student_id": "phone-b"}).json()["polls"][0]
    assert "counts" not in other
    remote = client.post(
        f"/api/rooms/{room_id}/polls/{poll['id']}/answers",
        json={"student_id": "phone-b", "option": "No", "seat_zone": "remote"},
    )
    assert remote.status_code == 200
    assert remote.json()["counts"] == {"Yes": 1, "No": 1}
    blank = client.post(
        f"/api/rooms/{room_id}/polls/{poll['id']}/answers",
        json={"student_id": "phone-c", "option": "Yes", "seat_zone": ""},
    )
    assert blank.status_code == 400
    assert blank.json()["error"] == "bad_zone"


def test_questions_are_anonymous_and_one_upvote_each():
    client = _client()
    room_id = _room(client)
    asked = client.post(
        f"/api/rooms/{room_id}/questions",
        json={"student_id": "phone-a", "text": "Can you repeat the definition?"},
    )
    assert asked.status_code == 200
    question_id = asked.json()["id"]
    later = client.post(
        f"/api/rooms/{room_id}/questions",
        json={"student_id": "phone-b", "text": "Is the homework due Friday?"},
    )
    assert later.status_code == 200
    later_id = later.json()["id"]

    empty = client.post(f"/api/rooms/{room_id}/questions", json={"student_id": "phone-a", "text": "  "})
    assert empty.status_code == 400
    assert empty.json()["error"] == "missing_question"

    own = client.post(
        f"/api/rooms/{room_id}/questions/{question_id}/upvote",
        json={"student_id": "phone-a"},
    )
    assert own.status_code == 200
    assert own.json()["votes"] == 1
    again = client.post(
        f"/api/rooms/{room_id}/questions/{question_id}/upvote",
        json={"student_id": "phone-a"},
    )
    assert again.status_code == 400
    assert again.json()["error"] == "already_upvoted"

    seen = client.get(f"/api/rooms/{room_id}/questions", params={"student_id": "phone-b"})
    assert seen.status_code == 200
    body = seen.json()["questions"]
    assert [item["id"] for item in body] == [question_id, later_id]
    assert body[0]["votes"] == 1
    assert body[0]["upvoted"] is False
    assert body[0]["text"] == "Can you repeat the definition?"
    assert "phone-a" not in seen.text
    assert "student_id" not in seen.text
    boosted = client.post(
        f"/api/rooms/{room_id}/questions/{later_id}/upvote",
        json={"student_id": "phone-b"},
    )
    assert boosted.status_code == 200
    ordered = client.get(f"/api/rooms/{room_id}/questions").json()["questions"]
    assert [item["id"] for item in ordered] == [question_id, later_id]
    client.post(f"/api/rooms/{room_id}/questions/{later_id}/upvote", json={"student_id": "phone-a"})
    ordered = client.get(f"/api/rooms/{room_id}/questions", params={"student_id": "phone-b"}).json()["questions"]
    assert ordered[0]["id"] == later_id
    assert ordered[0]["votes"] == 2
    assert ordered[0]["upvoted"] is True
    assert "phone-a" not in client.get(f"/api/rooms/{room_id}/questions").text

    client.post(f"/api/rooms/{room_id}/close", headers={"x-lecturer-token": TOKEN})
    closed = client.post(
        f"/api/rooms/{room_id}/questions",
        json={"student_id": "phone-a", "text": "Too late?"},
    )
    assert closed.status_code == 409
    assert closed.json()["error"] == "room_closed"
    still = client.get(f"/api/rooms/{room_id}/questions")
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

    student = client.get(f"/api/rooms/{room_id}/summary")
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
    early = client.get(f"/api/rooms/{room_id}/summary")
    assert early.json()["published"] is True
    assert early.json()["text"] == ""
    assert "HMAC is the integrity story" not in early.text
    lecturer = client.get(f"/api/rooms/{room_id}/summary", headers={"x-lecturer-token": TOKEN}).json()
    assert lecturer["draft"] == "HMAC is the integrity story. Revisit the definition."
    assert "api_key" not in lecturer

    client.post(f"/api/rooms/{room_id}/close", headers={"x-lecturer-token": TOKEN})
    visible = client.get(f"/api/rooms/{room_id}/summary")
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
    client.post(f"/api/rooms/{room_id}/close", headers={"x-lecturer-token": TOKEN})
    assert client.get(f"/api/rooms/{room_id}/summary").json()["text"].startswith("Written by hand")
