"""Flickering screen QR: 2s live hold, freshness, replay, and the network gate."""

from fastapi.testclient import TestClient

from app.main import create_app
from app.screen_qr import ScreenQrError, ScreenQrService
from tests.conftest import make_settings, signed_request
from tests.test_roster_presence import (
    _arm,
    _auth,
    _client,
    _names,
    _observe,
    _qr_codes,
    _room,
    _submit_qr,
    TOKEN,
)


def _identify(client, room_id, display="דנה לוי", email=None, attempt="phone"):
    emails = {"דנה לוי": "dana@example.test", "יוסי כהן": "yosi@example.test"}
    if email is None:
        email = emails[display]
    person = next(item for item in _names(client, room_id) if item["display"] == display)
    identified = client.post(
        f"/api/rooms/{room_id}/roster/identify",
        json={"entry_id": person["id"], "email": email, "attempt": attempt},
    )
    assert identified.status_code == 200, identified.text
    body = identified.json()
    body["_entry_id"] = person["id"]
    return body


def _align(application, room_id, when=1_700_000_010.0):
    book = application.state.store.get(room_id).presence
    book._clock = lambda t=when: t
    return book


def test_lecturer_token_is_required_to_read_the_current_frame():
    _application, client = _client()
    room_id = _room(client)
    denied = client.get(f"/api/rooms/{room_id}/presence/screen-qr")
    assert denied.status_code == 401
    helper = _arm(client, room_id)
    assert helper
    allowed = client.get(f"/api/rooms/{room_id}/presence/screen-qr", headers=_auth())
    assert allowed.status_code == 200
    body = allowed.json()
    assert body["code"].startswith("ZM1.")
    assert body["qr_needed"] == 5
    assert body["qr_min_distinct"] == 5
    assert body["qr_hold_seconds"] == 2
    assert body["qr_max_age_seconds"] == 6
    assert body["qr_frame_seconds"] == 0.25
    assert body["qr_flicker_hz"] == 20
    assert body["flicker_seed"]
    assert body["qr_required"] is True
    again = client.get(f"/api/rooms/{room_id}/presence/screen-qr", headers=_auth())
    assert again.json()["code"] == body["code"]
    assert again.json()["slot"] == body["slot"]
    assert again.json()["flicker_seed"] == body["flicker_seed"]


def test_valid_two_second_live_sequence_and_network_mark_the_roster():
    application, client = _client()
    room_id = _room(client)
    helper = _arm(client, room_id)
    identified = _identify(client, room_id)
    assert identified["qr_required"] is True
    assert identified["qr_hold_seconds"] == 2
    accepted = _submit_qr(client, identified, room_id, _qr_codes(application, room_id))
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["qr"] == "ready"
    assert accepted.json()["network"] == "pending"
    assert accepted.json()["in_class"] is False
    sheet = client.get(f"/api/rooms/{room_id}/roster", headers=_auth()).json()
    row = next(item for item in sheet["entries"] if item["id"] == identified["_entry_id"])
    assert row["in_class"] is False
    early = signed_request(
        client,
        identified,
        "POST",
        f"/api/rooms/{room_id}/presence/finish",
        {"challenge_id": identified["challenge_id"]},
    )
    assert early.status_code == 409
    assert early.json()["error"] == "presence_required"
    assert _observe(client, room_id, helper, identified["challenge_id"]).status_code == 200
    done = signed_request(
        client,
        identified,
        "POST",
        f"/api/rooms/{room_id}/presence/finish",
        {"challenge_id": identified["challenge_id"]},
    )
    assert done.status_code == 200
    assert done.json()["in_class"] is True
    assert done.json()["display"] == "דנה לוי"
    marked = client.get(f"/api/rooms/{room_id}/roster", headers=_auth())
    assert "6789" not in marked.text
    assert "123456789" not in marked.text
    assert "dana@example.test" not in marked.text
    row = next(item for item in marked.json()["entries"] if item["id"] == identified["_entry_id"])
    assert row["in_class"] is True


def test_network_check_is_still_required_after_a_valid_sequence():
    application, client = _client()
    room_id = _room(client)
    _arm(client, room_id)
    identified = _identify(client, room_id, attempt="qr-only")
    accepted = _submit_qr(client, identified, room_id, _qr_codes(application, room_id))
    assert accepted.status_code == 200
    done = signed_request(
        client,
        identified,
        "POST",
        f"/api/rooms/{room_id}/presence/finish",
        {"challenge_id": identified["challenge_id"]},
    )
    assert done.status_code == 409
    assert done.json()["error"] == "presence_required"
    row = next(
        item
        for item in client.get(f"/api/rooms/{room_id}/roster", headers=_auth()).json()["entries"]
        if item["id"] == identified["_entry_id"]
    )
    assert row["in_class"] is False


def test_network_without_the_sequence_is_not_enough():
    _application, client = _client()
    room_id = _room(client)
    helper = _arm(client, room_id)
    identified = _identify(client, room_id, attempt="net-only")
    assert _observe(client, room_id, helper, identified["challenge_id"]).status_code == 200
    done = signed_request(
        client,
        identified,
        "POST",
        f"/api/rooms/{room_id}/presence/finish",
        {"challenge_id": identified["challenge_id"]},
    )
    assert done.status_code == 409
    assert done.json()["error"] == "qr_required"
    row = next(
        item
        for item in client.get(f"/api/rooms/{room_id}/roster", headers=_auth()).json()["entries"]
        if item["id"] == identified["_entry_id"]
    )
    assert row["in_class"] is False


def test_static_or_repeated_frame_is_rejected():
    application, client = _client()
    room_id = _room(client)
    _arm(client, room_id)
    identified = _identify(client, room_id, attempt="static")
    book = _align(application, room_id)
    current = book.screen_qr.slot_for(book.now())
    one = book.screen_qr.issue_at(application.state.store.get(room_id).key, room_id, current, now=book.now()).code
    photo = _submit_qr(client, identified, room_id, [one])
    assert photo.status_code == 409
    assert photo.json()["error"] == "qr_static"
    repeated = _submit_qr(client, identified, room_id, [one] * 8)
    assert repeated.status_code == 409
    assert repeated.json()["error"] == "qr_static"
    live = _submit_qr(client, identified, room_id, _qr_codes(application, room_id))
    assert live.status_code == 200, live.text


def test_too_short_capture_is_rejected():
    application, client = _client()
    room_id = _room(client)
    _arm(client, room_id)
    identified = _identify(client, room_id, attempt="short")
    book = _align(application, room_id)
    now = book.now()
    current = book.screen_qr.slot_for(now)
    key = application.state.store.get(room_id).key
    # Four consecutive 250ms frames cover only one second.
    short = [
        book.screen_qr.issue_at(key, room_id, current - 3 + i, now=now).code
        for i in range(4)
    ]
    rejected = _submit_qr(client, identified, room_id, short)
    assert rejected.status_code == 409
    assert rejected.json()["error"] == "qr_short"
    # Five frames still cover only 1.25s, so liveness fails even at min_distinct.
    almost = [
        book.screen_qr.issue_at(key, room_id, current - 4 + i, now=now).code
        for i in range(5)
    ]
    still = _submit_qr(client, identified, room_id, almost)
    assert still.status_code == 409
    assert still.json()["error"] == "qr_short"
    ok = _submit_qr(client, identified, room_id, _qr_codes(application, room_id))
    assert ok.status_code == 200, ok.text


def test_stale_frame_older_than_max_age_is_rejected():
    application, client = _client()
    room_id = _room(client)
    _arm(client, room_id)
    identified = _identify(client, room_id, attempt="stale")
    start = 1_700_000_010.0
    book = _align(application, room_id, start)
    codes = _qr_codes(application, room_id)
    book._clock = lambda: start + 6.1
    stale = _submit_qr(client, identified, room_id, codes)
    assert stale.status_code == 409
    assert stale.json()["error"] == "qr_stale"
    book._clock = lambda: start
    ok = _submit_qr(client, identified, room_id, _qr_codes(application, room_id))
    assert ok.status_code == 200, ok.text


def test_replayed_code_is_rejected():
    application, client = _client()
    room_id = _room(client)
    _arm(client, room_id)
    first = _identify(client, room_id, attempt="replay-a")
    codes = _qr_codes(application, room_id)
    assert _submit_qr(client, first, room_id, codes).status_code == 200
    again = _submit_qr(client, first, room_id, codes)
    assert again.status_code == 409
    assert again.json()["error"] == "qr_replay"
    other = _identify(client, room_id, display="יוסי כהן", attempt="replay-b")
    # The same displayed frames may be used by a different student.
    shared = _submit_qr(client, other, room_id, codes)
    assert shared.status_code == 200, shared.text


def test_wrong_room_code_is_rejected():
    application, client = _client()
    room_id = _room(client)
    _arm(client, room_id)
    other = _room(client)
    _arm(client, other)
    identified = _identify(client, room_id, attempt="cross-room")
    foreign = _qr_codes(application, other)
    rejected = _submit_qr(client, identified, room_id, foreign)
    assert rejected.status_code == 401
    assert rejected.json()["error"] == "qr_mismatch"
    leaked = _submit_qr(client, identified, other, foreign)
    assert leaked.status_code == 401


def test_out_of_order_and_gapped_sequences_are_rejected():
    application, client = _client()
    room_id = _room(client)
    _arm(client, room_id)
    identified = _identify(client, room_id, attempt="order")
    book = _align(application, room_id)
    now = book.now()
    current = book.screen_qr.slot_for(now)
    key = application.state.store.get(room_id).key
    codes = [
        book.screen_qr.issue_at(key, room_id, current - 7 + i, now=now).code
        for i in range(8)
    ]
    swapped = list(codes)
    swapped[2], swapped[3] = swapped[3], swapped[2]
    out_of_order = _submit_qr(client, identified, room_id, swapped)
    assert out_of_order.status_code == 409
    assert out_of_order.json()["error"] == "qr_sequence"
    # A gap wider than three slots is not a live camera hold.
    wide = [
        book.screen_qr.issue_at(key, room_id, current - 7, now=now).code,
        book.screen_qr.issue_at(key, room_id, current - 2, now=now).code,
        book.screen_qr.issue_at(key, room_id, current - 1, now=now).code,
        book.screen_qr.issue_at(key, room_id, current, now=now).code,
        book.screen_qr.issue_at(key, room_id, current + 1, now=now + 0.25).code,
    ]
    # current+1 may look slightly future if clock is pinned; issue it at now anyway
    # (slot current+1 issued_at is only 0.25s ahead; verify_one allows -0.5s).
    gapped = _submit_qr(client, identified, room_id, wide)
    assert gapped.status_code == 409
    assert gapped.json()["error"] in {"qr_sequence", "qr_short"}
    ok = _submit_qr(client, identified, room_id, codes)
    assert ok.status_code == 200, ok.text


def test_missed_frames_within_the_gap_limit_still_pass():
    application, client = _client()
    room_id = _room(client)
    _arm(client, room_id)
    identified = _identify(client, room_id, attempt="gaps")
    book = _align(application, room_id)
    now = book.now()
    current = book.screen_qr.slot_for(now)
    key = application.state.store.get(room_id).key
    # Camera missed a couple of 250ms slots but still covered two seconds
    # with five changing codes and gaps of at most two slots.
    sparse = [
        book.screen_qr.issue_at(key, room_id, current - 7, now=now).code,
        book.screen_qr.issue_at(key, room_id, current - 5, now=now).code,
        book.screen_qr.issue_at(key, room_id, current - 3, now=now).code,
        book.screen_qr.issue_at(key, room_id, current - 1, now=now).code,
        book.screen_qr.issue_at(key, room_id, current, now=now).code,
    ]
    ok = _submit_qr(client, identified, room_id, sparse)
    assert ok.status_code == 200, ok.text


def test_toggle_off_allows_network_only_checkin():
    _application, client = _client()
    room_id = _room(client)
    helper = _arm(client, room_id)
    saved = client.post(
        f"/api/rooms/{room_id}/presence/screen-qr/settings",
        headers=_auth(),
        json={"required": False},
    )
    assert saved.status_code == 200
    assert saved.json()["qr_required"] is False
    identified = _identify(client, room_id, attempt="toggle-off")
    assert identified["qr_required"] is False
    assert _observe(client, room_id, helper, identified["challenge_id"]).status_code == 200
    done = signed_request(
        client,
        identified,
        "POST",
        f"/api/rooms/{room_id}/presence/finish",
        {"challenge_id": identified["challenge_id"]},
    )
    assert done.status_code == 200
    assert done.json()["in_class"] is True


def test_phone_clock_is_not_used_for_freshness():
    service = ScreenQrService()
    key = b"k" * 32
    # 1_700_000_010 is an exact 0.25-second slot boundary.
    issued = 1_700_000_010.0
    slot = service.slot_for(issued)
    assert slot * service.frame_seconds == issued
    frame = service.issue_at(key, "abc123", slot, now=issued)
    ok = service.verify_one(key, "abc123", frame.code, now=issued + 6.0)
    assert ok.slot == frame.slot
    try:
        service.verify_one(key, "abc123", frame.code, now=issued + 6.1)
        raised = False
    except Exception as exc:
        raised = getattr(exc, "reason", "") == "qr_stale"
    assert raised


def test_each_code_stays_on_the_same_slot_for_a_quarter_second():
    times = {"t": 1_700_000_010.0}
    service = ScreenQrService(clock=lambda: times["t"])
    key = b"k" * 32
    first = service.issue(key, "abc123")
    times["t"] = 1_700_000_010.0 + 0.24
    same = service.issue(key, "abc123")
    assert same.slot == first.slot
    assert same.code == first.code
    times["t"] = 1_700_000_010.0 + 0.25
    nxt = service.issue(key, "abc123")
    assert nxt.slot == first.slot + 1
    assert nxt.code != first.code
    still = service.verify_one(key, "abc123", first.code, now=times["t"])
    assert still.slot == first.slot


def test_freshness_is_judged_per_code_at_receipt():
    """A 2s capture does not fill the freshness window the way 3x1.5s did."""
    service = ScreenQrService()
    key = b"k" * 32
    issued = 1_700_000_010.0
    start = service.slot_for(issued) - 7
    codes = [service.issue_at(key, "abc123", start + i, now=issued).code for i in range(8)]
    # Received 0.4s after the last frame ended: oldest is 2.15s old, well
    # inside the 6s receipt window, so a slightly slow phone still passes.
    frames = service.verify_sequence(key, "abc123", codes, now=issued + 0.4)
    assert len(frames) == 8
    assert service.coverage_seconds(frames) == 2.0
    try:
        service.verify_sequence(key, "abc123", codes, now=issued + 6.1)
        raised = False
    except ScreenQrError as exc:
        raised = exc.reason == "qr_stale"
    assert raised
