import base64

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_device, make_settings

TOKEN = "lecturer-test-token"


def _client():
    return TestClient(create_app(make_settings()))


def _room(client):
    created = client.post(
        "/api/rooms",
        headers={"x-lecturer-token": TOKEN},
        json={"title": "Lesson"},
    ).json()
    return created["id"]


def test_remote_join_needs_no_device_and_returns_a_server_marker():
    client = _client()
    room_id = _room(client)
    joined = client.post(f"/api/rooms/{room_id}/remote-join")
    assert joined.status_code == 200
    marker = joined.json()["marker"]
    assert joined.json()["mode"] == "remote"
    assert len(marker) >= 8
    sheet = client.get(f"/api/rooms/{room_id}/attendance", headers={"x-lecturer-token": TOKEN}).json()
    row = sheet["records"][0]
    assert row["mode"] == "remote"
    assert row["attendance_id"] == marker
    assert row["external_token"] == marker
    assert "signature" not in joined.text


def test_in_class_attendance_id_comes_from_the_server():
    client = _client()
    room_id = _room(client)
    code = client.get(f"/api/rooms/{room_id}/token", headers={"x-lecturer-token": TOKEN}).json()["code"]
    device = make_device()
    opened = client.post(
        f"/api/rooms/{room_id}/challenge",
        json={"student_id": "stu-1", "device_id": device["device_id"], "public_jwk": device["jwk"]},
    ).json()
    signature = base64.b64encode(device["sign"](opened["challenge_id"], opened["nonce"])).decode()
    checked = client.post(
        f"/api/rooms/{room_id}/checkin",
        json={
            "challenge_id": opened["challenge_id"],
            "signature": signature,
            "mode": "in_class",
            "token_code": code,
            "seat_zone": "front-left",
            "student_name": "Ada",
        },
    )
    assert checked.status_code == 200
    attendance_id = checked.json()["attendance_id"]
    assert len(attendance_id) >= 8
    sheet = client.get(f"/api/rooms/{room_id}/attendance", headers={"x-lecturer-token": TOKEN}).json()
    assert sheet["records"][0]["attendance_id"] == attendance_id
    assert attendance_id != "stu-1"


def test_lesson_settings_select_band_and_proof():
    client = _client()
    room_id = _room(client)
    saved = client.post(
        f"/api/rooms/{room_id}/lesson-settings",
        headers={"x-lecturer-token": TOKEN},
        json={"audio_band": "audible", "proof": "qr"},
    )
    assert saved.status_code == 200
    assert saved.json() == {"audio_band": "audible", "proof": "qr"}
    public = client.get(f"/api/rooms/{room_id}").json()
    assert public["audio_band"] == "audible"
    assert public["proof"] == "qr"
    rejected = client.post(
        f"/api/rooms/{room_id}/lesson-settings",
        headers={"x-lecturer-token": TOKEN},
        json={"audio_band": "subsonic"},
    )
    assert rejected.status_code == 400
    assert rejected.json()["error"] == "bad_band"


def _check_in_without_id(client, room_id, device, code):
    opened = client.post(
        f"/api/rooms/{room_id}/challenge",
        json={"student_id": "", "device_id": device["device_id"], "public_jwk": device["jwk"]},
    )
    assert opened.status_code == 200
    opened = opened.json()
    signature = base64.b64encode(device["sign"](opened["challenge_id"], opened["nonce"])).decode()
    return client.post(
        f"/api/rooms/{room_id}/checkin",
        json={
            "challenge_id": opened["challenge_id"],
            "signature": signature,
            "mode": "in_class",
            "token_code": code,
            "seat_zone": "front-right",
            "student_name": "",
        },
    )


def test_in_class_check_in_needs_no_student_id_and_uses_the_server_id():
    client = _client()
    room_id = _room(client)
    code = client.get(f"/api/rooms/{room_id}/token", headers={"x-lecturer-token": TOKEN}).json()["code"]
    checked = _check_in_without_id(client, room_id, make_device(), code)
    assert checked.status_code == 200
    body = checked.json()
    assert len(body["attendance_id"]) >= 8
    assert body["student_id"] == body["attendance_id"]
    sheet = client.get(f"/api/rooms/{room_id}/attendance", headers={"x-lecturer-token": TOKEN}).json()
    assert sheet["records"][0]["student_id"] == body["attendance_id"]
    assert sheet["records"][0]["mode"] == "in_class"


def test_two_anonymous_phones_get_different_server_ids():
    client = _client()
    room_id = _room(client)
    code = client.get(f"/api/rooms/{room_id}/token", headers={"x-lecturer-token": TOKEN}).json()["code"]
    first = _check_in_without_id(client, room_id, make_device(), code).json()
    second = _check_in_without_id(client, room_id, make_device(), code).json()
    assert first["attendance_id"] != second["attendance_id"]
    assert not first["flags"] and not second["flags"]


def test_challenge_still_needs_a_device():
    client = _client()
    room_id = _room(client)
    opened = client.post(f"/api/rooms/{room_id}/challenge", json={"student_id": "", "device_id": "", "public_jwk": {}})
    assert opened.status_code == 400
    assert opened.json()["error"] == "missing_identity"


def test_lecturer_lists_open_rooms_only_with_the_token():
    client = _client()
    room_id = _room(client)
    other = _room(client)
    client.post(f"/api/rooms/{other}/close", headers={"x-lecturer-token": TOKEN})
    assert client.get("/api/rooms").status_code in (401, 403)
    listed = client.get("/api/rooms", headers={"x-lecturer-token": TOKEN})
    assert listed.status_code == 200
    ids = [room["id"] for room in listed.json()["rooms"]]
    assert room_id in ids and other not in ids
    assert listed.json()["rooms"][0]["counts"]["in_class"] == 0
