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
