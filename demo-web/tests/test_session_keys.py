"""Session keys: issued once, HMAC on later actions, absent from the lecturer desk."""

import base64
import json
import secrets as pysecrets
import time

from fastapi.testclient import TestClient

from app.main import create_app
from app.session_keys import canonical_message, decode_secret, derive_session_verifier, sign_message
from tests.conftest import make_device, make_settings, signed_request

TOKEN = "lecturer-test-token"


def _client():
    application = create_app(make_settings())
    return application, TestClient(application)


def _room(client, title="Graphs"):
    created = client.post(
        "/api/rooms",
        headers={"x-lecturer-token": TOKEN},
        json={"title": title},
    ).json()
    return created["id"]


def _check_in(client, room_id, zone="front-center"):
    code = client.get(f"/api/rooms/{room_id}/token", headers={"x-lecturer-token": TOKEN}).json()["code"]
    device = make_device()
    opened = client.post(
        f"/api/rooms/{room_id}/challenge",
        json={"student_id": "", "device_id": device["device_id"], "public_jwk": device["jwk"]},
    ).json()
    signature = base64.b64encode(device["sign"](opened["challenge_id"], opened["nonce"])).decode()
    checked = client.post(
        f"/api/rooms/{room_id}/checkin",
        json={
            "challenge_id": opened["challenge_id"],
            "signature": signature,
            "mode": "in_class",
            "token_code": code,
            "seat_zone": zone,
            "student_name": "Ada",
        },
    )
    assert checked.status_code == 200
    return checked.json()


def test_check_in_returns_the_secret_once_and_stores_only_the_verifier():
    application, client = _client()
    room_id = _room(client)
    body = _check_in(client, room_id)
    assert len(body["session_id"]) >= 8
    secret = decode_secret(body["session_key"])
    room = application.state.store.get(room_id)
    stored = room.sessions.sessions[body["session_id"]]
    assert stored.verifier == derive_session_verifier(secret)
    assert stored.verifier != secret
    assert not hasattr(stored, "secret")
    again = client.get(f"/api/rooms/{room_id}/attendance", headers={"x-lecturer-token": TOKEN})
    assert body["session_key"] not in again.text
    assert again.json()["records"][0]["verified"] is True
    remote = client.post(f"/api/rooms/{room_id}/remote-join").json()
    assert remote["session_key"] != body["session_key"]
    assert "session_key" not in client.get(f"/api/rooms/{room_id}").text


def test_forged_expired_and_replayed_signatures_are_rejected():
    _application, client = _client()
    room_id = _room(client)
    creds = _check_in(client, room_id)
    path = f"/api/rooms/{room_id}/questions"
    payload = {"student_id": creds["attendance_id"], "text": "What is a nonce?"}
    ok = signed_request(client, creds, "POST", path, payload)
    assert ok.status_code == 200

    raw = json.dumps({"student_id": creds["attendance_id"], "text": "Forged"}, separators=(",", ":")).encode()
    stamp = str(int(time.time()))
    nonce = pysecrets.token_hex(16)
    message = canonical_message("POST", path, raw, stamp, nonce)
    signature = sign_message(derive_session_verifier(decode_secret(creds["session_key"])), message)
    signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    forged = client.post(
        path,
        content=raw,
        headers={
            "content-type": "application/json",
            "x-zoomoodle-session": creds["session_id"],
            "x-zoomoodle-timestamp": stamp,
            "x-zoomoodle-nonce": nonce,
            "x-zoomoodle-signature": signature,
        },
    )
    assert forged.status_code == 401
    assert forged.json()["error"] == "bad_session"

    expired = signed_request(client, creds, "POST", path, payload, timestamp=int(time.time()) - 120)
    assert expired.status_code == 401
    assert expired.json()["error"] == "session_expired"

    replay_nonce = "cafebabe" * 4
    first = signed_request(
        client, creds, "POST", path, {"student_id": creds["attendance_id"], "text": "Once"}, nonce=replay_nonce
    )
    assert first.status_code == 200
    second = signed_request(
        client, creds, "POST", path, {"student_id": creds["attendance_id"], "text": "Once"}, nonce=replay_nonce
    )
    assert second.status_code == 401
    assert second.json()["error"] == "session_replay"


def test_close_revokes_writes_and_the_key_never_reaches_the_lecturer():
    _application, client = _client()
    room_id = _room(client)
    creds = _check_in(client, room_id, "front-left")
    key = creds["session_key"]
    overview = client.get(f"/api/rooms/{room_id}/overview", headers={"x-lecturer-token": TOKEN})
    assert overview.status_code == 200
    assert overview.json()["zones"]["front-left"] == 1
    assert overview.json()["zones"]["front-center"] == 0
    assert key not in overview.text
    csv_export = client.get(f"/api/rooms/{room_id}/export.csv", headers={"x-lecturer-token": TOKEN})
    xlsx_export = client.get(f"/api/rooms/{room_id}/export.xlsx", headers={"x-lecturer-token": TOKEN})
    attendance = client.get(f"/api/rooms/{room_id}/attendance", headers={"x-lecturer-token": TOKEN})
    assert key not in csv_export.text
    assert key.encode() not in xlsx_export.content
    assert key not in attendance.text
    assert "session_key" not in attendance.text
    assert attendance.json()["records"][0]["verified"] is True

    client.post(f"/api/rooms/{room_id}/close", headers={"x-lecturer-token": TOKEN})
    denied = signed_request(
        client,
        creds,
        "POST",
        f"/api/rooms/{room_id}/questions",
        {"student_id": creds["attendance_id"], "text": "After the bell?"},
    )
    assert denied.status_code == 401
    assert denied.json()["error"] == "session_revoked"
    closed_sheet = client.get(f"/api/rooms/{room_id}/attendance", headers={"x-lecturer-token": TOKEN}).json()
    assert closed_sheet["records"][0]["verified"] is False
    assert key not in client.get(f"/api/rooms/{room_id}/overview", headers={"x-lecturer-token": TOKEN}).text
