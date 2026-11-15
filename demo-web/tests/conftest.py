import json
import os
import secrets
import time

# Never touch the real ~/.zoomoodle key file from tests.
os.environ.setdefault("ZOOMODLE_LECTURER_KEY", "test-module-level-lecturer-key-0123456789")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.session_keys import canonical_message, decode_secret, derive_session_verifier, sign_message  # noqa: E402

LECTURER_KEY = "zmk_test-lecturer-key-which-is-long-enough"
CAMPUS_IP = "192.114.52.1"
HOME_IP = "84.229.10.20"
ROSTER = (
    "שם פרטי,שם משפחה,מספר זיהוי,דוא״ל\n"
    "דנה,לוי,123456789,dana@example.test\n"
    "יוסי,כהן,987654321,yosi@example.test\n"
    "עמית,שמש,111122223,amit@example.test\n"
)


def make_settings(**overrides) -> Settings:
    values = dict(
        master_secret=b"test-master-secret-which-is-long",
        lecturer_key=LECTURER_KEY,
        trusted_proxies=("127.0.0.1/32", "::1/128", "10.0.0.0/8"),
    )
    values.update(overrides)
    return Settings(**values)


def make_client(settings=None, mailer=None, peer=None):
    from app.main import create_app

    app = create_app(settings or make_settings(), mailer=mailer)
    client = TestClient(app, client=(peer or "10.1.2.3", 50000))
    return app, client


def login(client) -> dict:
    response = client.post("/api/lecturer/login", json={"key": LECTURER_KEY})
    assert response.status_code == 200, response.text
    return {"x-lecturer-session": response.json()["token"]}


def open_room(client, roster=ROSTER):
    headers = login(client)
    room = client.post("/api/rooms", json={}, headers=headers).json()
    imported = client.post(f"/api/rooms/{room['id']}/roster", json={"text": roster}, headers=headers)
    assert imported.status_code == 200, imported.text
    return room["id"], headers


def entry_id(client, room_id, display):
    names = client.get(f"/api/rooms/{room_id}/roster/names").json()["names"]
    return next(item["id"] for item in names if item["display"] == display)


def from_ip(ip):
    """Headers as Render's proxy (a trusted 10.x peer) would append them."""
    return {"x-forwarded-for": ip}


def signed(client, creds, method, path, payload=None, headers=None):
    body = b"" if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    stamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    verifier = derive_session_verifier(decode_secret(creds["session_key"]))
    all_headers = {
        "content-type": "application/json",
        "x-zoomoodle-session": creds["session_id"],
        "x-zoomoodle-timestamp": stamp,
        "x-zoomoodle-nonce": nonce,
        "x-zoomoodle-signature": sign_message(verifier, canonical_message(method, path, body, stamp, nonce)),
    }
    all_headers.update(headers or {})
    return client.request(method, path, content=body, headers=all_headers)


def live_codes(app, room_id, count=9):
    """A real 2+ second live capture: one code per 250 ms slot, ending now."""
    room = app.state.store.get(room_id)
    qr = room.screen_qr
    now = qr.now()
    last = qr.slot_for(now)
    return [qr.issue_at(room.key, room.id, slot, now=now).code for slot in range(last - count + 1, last + 1)]


def join(client, room_id, display, mode, ip=CAMPUS_IP):
    eid = entry_id(client, room_id, display)
    return client.post(f"/api/rooms/{room_id}/join", json={"entry_id": eid, "mode": mode}, headers=from_ip(ip))


def check_in_class(app, client, room_id, display, zone="front-center", ip=CAMPUS_IP):
    joined = join(client, room_id, display, "in_class", ip)
    assert joined.status_code == 200, joined.text
    creds = joined.json()
    scanned = signed(client, creds, "POST", f"/api/rooms/{room_id}/barcode", {"codes": live_codes(app, room_id)}, from_ip(ip))
    assert scanned.status_code == 200, scanned.text
    if scanned.json()["state"] != "pending_barcode" and zone:
        area = signed(client, creds, "POST", f"/api/rooms/{room_id}/area", {"zone": zone})
        assert area.status_code == 200, area.text
    return creds
