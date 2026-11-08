"""Roster import, last-four check, and hotspot presence proof."""

import io
import json

from fastapi.testclient import TestClient

from app.main import create_app
from app.presence import derive_helper_verifier
from app.session_keys import decode_secret
from helper.hotspot_check import apply_hotspot, capability
from helper.presence_helper import PresenceHelper, connection_matches_bind, student_return
from tests.conftest import make_settings, signed_request

TOKEN = "lecturer-test-token"
CSV = ( __import__("pathlib").Path(__file__).parent / "fixtures" / "roster_sample.csv").read_text(encoding="utf-8")


def _client():
    application = create_app(make_settings())
    return application, TestClient(application)


def _room(client):
    created = client.post("/api/rooms", headers={"x-lecturer-token": TOKEN}, json={"title": "Graphs"}).json()
    return created["id"]


def _auth():
    return {"x-lecturer-token": TOKEN}


def _import(client, room_id, text=CSV):
    response = client.post(f"/api/rooms/{room_id}/roster", headers=_auth(), json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def _arm(client, room_id, group="3"):
    _import(client, room_id)
    chosen = client.post(
        f"/api/rooms/{room_id}/roster/group",
        headers=_auth(),
        json={"group": group},
    )
    assert chosen.status_code == 200
    paired = client.post(f"/api/rooms/{room_id}/presence/pair", headers=_auth())
    assert paired.status_code == 200
    bound = client.post(
        f"/api/rooms/{room_id}/presence/bind",
        headers=_auth(),
        json={"url": "http://192.168.137.1:8787"},
    )
    assert bound.status_code == 200
    return paired.json()


def _names(client, room_id):
    listed = client.get(f"/api/rooms/{room_id}/roster/names")
    assert listed.status_code == 200
    return listed.json()["names"]


def _observe(client, room_id, helper, challenge_id, when=None):
    import secrets
    import time

    from app.presence import sign_helper
    from app.session_keys import canonical_message, decode_secret

    path = f"/api/rooms/{room_id}/presence/observe"
    raw = json.dumps({"challenge_id": challenge_id}, separators=(",", ":")).encode("utf-8")
    stamp = str(int(time.time() if when is None else when))
    nonce = secrets.token_hex(16)
    message = canonical_message("POST", path, raw, stamp, nonce)
    signature = sign_helper(decode_secret(helper["helper_key"]), message)
    return client.post(
        path,
        content=raw,
        headers={
            "content-type": "application/json",
            "x-zoomoodle-session": helper["helper_id"],
            "x-zoomoodle-timestamp": stamp,
            "x-zoomoodle-nonce": nonce,
            "x-zoomoodle-signature": signature,
        },
    )


def test_csv_handles_hebrew_whitespace_duplicates_and_drops_secrets(capsys):
    application, client = _client()
    room_id = _room(client)
    denied = client.post(f"/api/rooms/{room_id}/roster", json={"text": CSV})
    assert denied.status_code == 401
    imported = _import(client, room_id)
    assert imported["imported"] == 5
    assert imported["duplicates"] == 1
    assert imported["skipped"] >= 1
    assert imported["groups"]["3"] == 3
    assert imported["groups"][""] == 1
    assert imported["groups"]["4"] == 1
    blob = json.dumps(imported)
    for secret in ("123456789", "dana@example.test", "987654321", "111122223"):
        assert secret not in blob
    captured = capsys.readouterr()
    assert "123456789" not in captured.out + captured.err
    room = application.state.store.get(room_id)
    stored = json.dumps(
        [
            {"given": entry.given, "family": entry.family, "group": entry.group}
            for entry in room.roster.entries.values()
        ]
    )
    assert "123456789" not in stored
    assert "dana@example.test" not in stored
    assert all(len(entry.verifier) == 32 for entry in room.roster.entries.values())


def test_blank_group_is_not_selected_until_the_lecturer_says_so():
    _application, client = _client()
    room_id = _room(client)
    rows = ["שם פרטי,שם משפחה,מספר זיהוי,דוא״ל,קבוצות"]
    for index in range(102):
        rows.append(f"תלמיד,מספר{index},{100000000 + index},s{index}@example.test,3")
    rows.append("צוות,אחד,200000001,staff1@example.test,")
    rows.append("צוות,שתיים,200000002,staff2@example.test, ")
    _import(client, room_id, "\n".join(rows))
    assert _names(client, room_id) == []
    listed = client.post(
        f"/api/rooms/{room_id}/roster/group",
        headers=_auth(),
        json={"group": "3"},
    ).json()
    assert listed["listed"] == 102
    names = _names(client, room_id)
    assert len(names) == 102
    assert all("צוות" not in item["display"] for item in names)
    unspecified = client.post(
        f"/api/rooms/{room_id}/roster/group",
        headers=_auth(),
        json={"include_unspecified": True},
    )
    assert unspecified.status_code == 200
    blank_names = _names(client, room_id)
    assert len(blank_names) == 2
    assert {item["display"] for item in blank_names} == {"צוות אחד", "צוות שתיים"}
    refused = client.post(f"/api/rooms/{room_id}/roster/group", headers=_auth(), json={"group": "  "})
    assert refused.status_code == 400


def test_pin_lock_and_name_list_hide_the_secret():
    _application, client = _client()
    room_id = _room(client)
    _arm(client, room_id)
    names = _names(client, room_id)
    dana = next(item for item in names if item["display"] == "דנה לוי")
    text = client.get(f"/api/rooms/{room_id}/roster/names").text
    assert "6789" not in text
    assert "123456789" not in text
    wrong = client.post(
        f"/api/rooms/{room_id}/roster/identify",
        json={"entry_id": dana["id"], "pin": "0000", "attempt": "browser-a"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["error"] == "identity_rejected"
    assert "6789" not in wrong.text
    for _ in range(4):
        client.post(
            f"/api/rooms/{room_id}/roster/identify",
            json={"entry_id": dana["id"], "pin": "0000", "attempt": "browser-a"},
        )
    limited = client.post(
        f"/api/rooms/{room_id}/roster/identify",
        json={"entry_id": dana["id"], "pin": "6789", "attempt": "browser-a"},
    )
    assert limited.status_code == 429
    assert limited.json()["error"] == "identity_limited"
    other = next(item for item in names if item["display"] == "יוסי כהן")
    # A different person is not locked by Dana's failures.
    ok = client.post(
        f"/api/rooms/{room_id}/roster/identify",
        json={"entry_id": other["id"], "pin": "4321", "attempt": "browser-b"},
    )
    assert ok.status_code == 200
    assert ok.json()["display"] == "יוסי כהן"
    assert "session_key" in ok.json()
    roster = client.get(f"/api/rooms/{room_id}/roster", headers=_auth()).json()
    yosi = next(row for row in roster["entries"] if row["display"] == "יוסי כהן")
    assert yosi["in_class"] is False
    again = client.get(f"/api/rooms/{room_id}/presence", headers=_auth())
    assert "helper_key" not in again.text


def test_presence_requires_helper_and_rejects_fake_replay_and_cross_use():
    application, client = _client()
    room_id = _room(client)
    helper = _arm(client, room_id)
    stored = application.state.store.get(room_id).presence.helper_verifier
    assert stored == derive_helper_verifier(decode_secret(helper["helper_key"]))
    assert stored != decode_secret(helper["helper_key"])
    dana = next(item for item in _names(client, room_id) if item["display"] == "דנה לוי")
    identified = client.post(
        f"/api/rooms/{room_id}/roster/identify",
        json={"entry_id": dana["id"], "pin": "6789", "attempt": "phone"},
    ).json()
    claim = signed_request(
        client,
        identified,
        "POST",
        f"/api/rooms/{room_id}/presence/finish",
        {"challenge_id": identified["challenge_id"], "ip": "192.168.137.20", "ssid": "ClassHotspot"},
    )
    assert claim.status_code == 409
    assert claim.json()["error"] == "presence_required"
    sheet = client.get(f"/api/rooms/{room_id}/roster", headers=_auth()).json()
    assert next(row for row in sheet["entries"] if row["id"] == dana["id"])["in_class"] is False

    bad = client.post(
        f"/api/rooms/{room_id}/presence/observe",
        json={"challenge_id": identified["challenge_id"], "ssid": "ClassHotspot"},
    )
    assert bad.status_code == 401

    seen = _observe(client, room_id, helper, identified["challenge_id"])
    assert seen.status_code == 200, seen.text
    other = next(item for item in _names(client, room_id) if item["display"] == "יוסי כהן")
    yosi = client.post(
        f"/api/rooms/{room_id}/roster/identify",
        json={"entry_id": other["id"], "pin": "4321", "attempt": "other"},
    ).json()
    crossed = signed_request(
        client,
        yosi,
        "POST",
        f"/api/rooms/{room_id}/presence/finish",
        {"challenge_id": identified["challenge_id"]},
    )
    assert crossed.status_code == 409
    assert crossed.json()["error"] == "presence_mismatch"

    done = signed_request(
        client,
        identified,
        "POST",
        f"/api/rooms/{room_id}/presence/finish",
        {"challenge_id": identified["challenge_id"]},
    )
    assert done.status_code == 200
    assert done.json()["in_class"] is True
    counts = signed_request(client, identified, "GET", f"/api/rooms/{room_id}/counts")
    assert counts.json()["in_class"] == 1
    replay = signed_request(
        client,
        identified,
        "POST",
        f"/api/rooms/{room_id}/presence/finish",
        {"challenge_id": identified["challenge_id"]},
    )
    assert replay.status_code == 409
    assert replay.json()["error"] == "presence_replay"
    marked = client.get(f"/api/rooms/{room_id}/roster", headers=_auth()).text
    assert "6789" not in marked
    assert "123456789" not in marked
    row = next(item for item in client.get(f"/api/rooms/{room_id}/roster", headers=_auth()).json()["entries"] if item["id"] == dana["id"])
    assert row["in_class"] is True
    assert row["remote"] is False

    exported = client.get(f"/api/rooms/{room_id}/export.csv", headers=_auth())
    assert "123456789" not in exported.text
    assert "6789" not in exported.text
    assert helper["helper_key"] not in exported.text


def test_stale_cross_room_revoke_close_and_remote_are_separate():
    application, client = _client()
    room_id = _room(client)
    helper = _arm(client, room_id)
    other_room = _room(client)
    dana = next(item for item in _names(client, room_id) if item["display"] == "דנה לוי")
    identified = client.post(
        f"/api/rooms/{room_id}/roster/identify",
        json={"entry_id": dana["id"], "pin": "6789", "attempt": "phone"},
    ).json()
    book = application.state.store.get(room_id).presence
    start = book.now()
    book._clock = lambda: start + 120
    stale = _observe(client, room_id, helper, identified["challenge_id"], when=start + 120)
    assert stale.status_code == 409
    assert stale.json()["error"] == "presence_expired"
    book._clock = lambda: start

    fresh = client.post(
        f"/api/rooms/{room_id}/roster/identify",
        json={"entry_id": dana["id"], "pin": "6789", "attempt": "phone-2"},
    ).json()
    leaked = _observe(client, other_room, helper, fresh["challenge_id"])
    assert leaked.status_code == 401

    client.post(f"/api/rooms/{room_id}/presence/revoke", headers=_auth())
    revoked = _observe(client, room_id, helper, fresh["challenge_id"])
    assert revoked.status_code == 401
    assert revoked.json()["error"] == "bad_helper"

    helper = client.post(f"/api/rooms/{room_id}/presence/pair", headers=_auth()).json()
    client.post(
        f"/api/rooms/{room_id}/presence/bind",
        headers=_auth(),
        json={"url": "http://192.168.137.1:8787"},
    )
    again = client.post(
        f"/api/rooms/{room_id}/roster/identify",
        json={"entry_id": dana["id"], "pin": "6789", "attempt": "phone-3"},
    ).json()
    assert _observe(client, room_id, helper, again["challenge_id"]).status_code == 200
    client.post(f"/api/rooms/{room_id}/close", headers=_auth())
    closed = signed_request(
        client,
        again,
        "POST",
        f"/api/rooms/{room_id}/presence/finish",
        {"challenge_id": again["challenge_id"]},
    )
    assert closed.status_code == 401
    assert closed.json()["error"] == "session_revoked"

    room_two = _room(client)
    _arm(client, room_two)
    person = next(item for item in _names(client, room_two) if item["display"] == "דנה לוי")
    remote = client.post(
        f"/api/rooms/{room_two}/roster/identify",
        json={"entry_id": person["id"], "pin": "6789", "attempt": "remote"},
    ).json()
    marked = signed_request(client, remote, "POST", f"/api/rooms/{room_two}/roster/remote", {})
    assert marked.status_code == 200
    assert marked.json()["mode"] == "remote"
    assert marked.json()["in_class"] is False
    row = next(item for item in client.get(f"/api/rooms/{room_two}/roster", headers=_auth()).json()["entries"] if item["id"] == person["id"])
    assert row["in_class"] is False
    assert row["remote"] is True


def test_helper_rejects_the_wrong_interface_and_hotspot_changes_nothing():
    macos = capability("darwin")
    windows = capability("win32")
    assert macos["automated"] is False and macos["will_change_settings"] is False
    assert windows["automated"] is False
    assert "netsh wlan start hostednetwork" in windows["not_used"]
    assert apply_hotspot("darwin", opt_in=False)["changed"] is False
    assert apply_hotspot("darwin", opt_in=True)["reason"] == "no_supported_automation"
    assert apply_hotspot("win32", opt_in=True)["changed"] is False
    source = open(capability.__code__.co_filename, encoding="utf-8").read()
    assert "subprocess" not in source
    assert connection_matches_bind(("192.168.137.1", 8787), "192.168.137.1")
    assert not connection_matches_bind(("10.0.0.5", 8787), "192.168.137.1")
    assert not connection_matches_bind(("0.0.0.0", 8787), "192.168.137.1")
    from app.session_keys import encode_secret

    helper = PresenceHelper(
        "192.168.137.1",
        "http://127.0.0.1:9",
        "abc123",
        "helper",
        encode_secret(b"\x11" * 32),
        "https://class.example",
    )
    status, _location = helper.prove("c" * 32, ("10.0.0.5", 8787))
    assert status == 403
    assert helper.observations == 0
    try:
        PresenceHelper("0.0.0.0", "http://127.0.0.1", "abc", "h", "A", "https://class.example")
        raised = False
    except ValueError:
        raised = True
    assert raised
    assert student_return("https://class.example", "abc123", "deadbeef") == "https://class.example/student?room=abc123#presence=deadbeef"


def test_source_search_does_not_call_a_model_or_send_the_roster():
    application, client = _client()
    room_id = _room(client)
    _arm(client, room_id)
    created = client.post(
        f"/api/rooms/{room_id}/sources",
        headers=_auth(),
        json={"title": "HMAC", "text": "HMAC proves integrity of a message.\nIt is not encryption."},
    )
    assert created.status_code == 200
    asked = client.post(
        f"/api/rooms/{room_id}/ask",
        json={"question": "What does HMAC prove?", "source_ids": [created.json()["id"]]},
    )
    assert asked.status_code == 200
    body = asked.json()
    assert body["mode"] == "source_search"
    assert body["model"] == "off"
    assert "integrity" in body["answer"]
    assert "דנה" not in asked.text
    calls = {"n": 0}

    class Scripted:
        def complete(self, messages, tools, max_tokens=1200):
            calls["n"] += 1
            joined = "\n".join(message.content for message in messages)
            assert "דנה לוי" not in joined
            assert "123456789" not in joined

            class Result:
                text = "integrity, from the source"

            return Result()

    application.state.provider_factory = lambda _config: Scripted()
    application.state.store.llm.provider = "openai"
    application.state.store.llm.model = "gpt-test"
    application.state.store.llm.api_key = "sk-test"
    still = client.post(f"/api/rooms/{room_id}/ask", json={"question": "HMAC"})
    assert still.json()["mode"] == "source_search"
    assert calls["n"] == 0
    client.post(f"/api/rooms/{room_id}/sources/model", headers=_auth(), json={"enabled": True})
    modeled = client.post(f"/api/rooms/{room_id}/ask", json={"question": "What does HMAC prove?"})
    assert modeled.status_code == 200
    assert modeled.json()["mode"] == "model"
    assert calls["n"] == 1
