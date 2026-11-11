from tests.conftest import (
    CAMPUS_IP,
    HOME_IP,
    check_in_class,
    entry_id,
    join,
    live_codes,
    make_client,
    open_room,
    signed,
)


def _dashboard(client, room_id, headers):
    return client.get(f"/api/rooms/{room_id}/dashboard", headers=headers).json()


def test_in_class_needs_campus_network_and_live_barcode_then_area():
    app, client = make_client()
    room_id, headers = open_room(client)
    joined = join(client, room_id, "דנה לוי", "in_class")
    assert joined.status_code == 200
    creds = joined.json()
    assert creds["state"] == "pending_barcode" and not creds["checked"]
    # Not counted before the barcode.
    assert _dashboard(client, room_id, headers)["counts"]["in_class"] == 0
    # Area cannot be chosen before the barcode.
    early = signed(client, creds, "POST", f"/api/rooms/{room_id}/area", {"zone": "back-left"})
    assert early.status_code == 409
    scanned = signed(client, creds, "POST", f"/api/rooms/{room_id}/barcode", {"codes": live_codes(app, room_id)}, {"x-forwarded-for": CAMPUS_IP})
    assert scanned.status_code == 200 and scanned.json()["state"] == "needs_area"
    area = signed(client, creds, "POST", f"/api/rooms/{room_id}/area", {"zone": "back-left"})
    assert area.status_code == 200
    body = area.json()
    assert body["checked"] and body["state"] == "present" and body["zone"] == "back-left"
    assert body["welcome"] == "ברוך הבא דנה לוי"
    dash = _dashboard(client, room_id, headers)
    assert dash["counts"]["in_class"] == 1 and dash["zones"]["back-left"] == 1
    assert dash["students"][0]["checked"] is True


def test_bad_area_is_rejected():
    app, client = make_client()
    room_id, _ = open_room(client)
    creds = check_in_class(app, client, room_id, "דנה לוי", zone=None)
    bad = signed(client, creds, "POST", f"/api/rooms/{room_id}/area", {"zone": "roof"})
    assert bad.status_code == 400


def test_out_of_range_ip_cannot_choose_in_class():
    _app, client = make_client()
    room_id, _ = open_room(client)
    response = join(client, room_id, "דנה לוי", "in_class", ip=HOME_IP)
    assert response.status_code == 403
    assert response.json()["error"] == "not_on_campus_network"


def test_network_is_checked_again_when_the_barcode_arrives():
    app, client = make_client()
    room_id, _ = open_room(client)
    creds = join(client, room_id, "דנה לוי", "in_class").json()
    moved = signed(client, creds, "POST", f"/api/rooms/{room_id}/barcode", {"codes": live_codes(app, room_id)}, {"x-forwarded-for": HOME_IP})
    assert moved.status_code == 403


def test_still_photo_and_short_capture_are_rejected():
    app, client = make_client()
    room_id, _ = open_room(client)
    creds = join(client, room_id, "דנה לוי", "in_class").json()
    codes = live_codes(app, room_id)
    still = signed(client, creds, "POST", f"/api/rooms/{room_id}/barcode", {"codes": [codes[-1]] * 9}, {"x-forwarded-for": CAMPUS_IP})
    assert still.json()["error"] == "qr_static"
    short = signed(client, creds, "POST", f"/api/rooms/{room_id}/barcode", {"codes": codes[-3:]}, {"x-forwarded-for": CAMPUS_IP})
    assert short.json()["error"] == "qr_short"


def test_barcode_from_another_room_and_replay_are_rejected():
    app, client = make_client()
    room_a, headers = open_room(client)
    room_b = client.post("/api/rooms", json={}, headers=headers).json()["id"]
    creds = join(client, room_a, "דנה לוי", "in_class").json()
    wrong = signed(client, creds, "POST", f"/api/rooms/{room_a}/barcode", {"codes": live_codes(app, room_b)}, {"x-forwarded-for": CAMPUS_IP})
    assert wrong.json()["error"] == "qr_mismatch"
    codes = live_codes(app, room_a)
    assert signed(client, creds, "POST", f"/api/rooms/{room_a}/barcode", {"codes": codes}, {"x-forwarded-for": CAMPUS_IP}).status_code == 200
    second = join(client, room_a, "דנה לוי", "in_class").json()
    replay = signed(client, second, "POST", f"/api/rooms/{room_a}/barcode", {"codes": codes}, {"x-forwarded-for": CAMPUS_IP})
    assert replay.json()["error"] == "qr_replay"


def test_remote_path_needs_no_network_or_barcode():
    _app, client = make_client()
    room_id, headers = open_room(client)
    response = join(client, room_id, "יוסי כהן", "remote", ip=HOME_IP)
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "remote" and body["checked"] and body["welcome"] == "ברוך הבא יוסי כהן"
    counts = _dashboard(client, room_id, headers)["counts"]
    assert counts["remote"] == 1 and counts["in_class"] == 0


def test_spoofed_forwarding_headers_do_not_pass_the_network_check():
    _app, client = make_client(peer="84.229.10.20")  # browser talks to us directly, not via the proxy
    room_id, _ = open_room(client)
    eid = entry_id(client, room_id, "דנה לוי")
    for forged in ({"x-forwarded-for": CAMPUS_IP}, {"cf-connecting-ip": CAMPUS_IP}, {"x-real-ip": CAMPUS_IP}):
        response = client.post(f"/api/rooms/{room_id}/join", json={"entry_id": eid, "mode": "in_class"}, headers=forged)
        assert response.status_code == 403, forged


def test_leftmost_forwarded_hop_from_the_browser_is_ignored():
    _app, client = make_client()  # peer is the trusted proxy 10.1.2.3
    room_id, _ = open_room(client)
    eid = entry_id(client, room_id, "דנה לוי")
    forged = {"x-forwarded-for": f"{CAMPUS_IP}, {HOME_IP}"}
    response = client.post(f"/api/rooms/{room_id}/join", json={"entry_id": eid, "mode": "in_class"}, headers=forged)
    assert response.status_code == 403
    # Render's peer is 10.x; Cloudflare's client header is the student IP.
    cf = client.post(
        f"/api/rooms/{room_id}/join",
        json={"entry_id": eid, "mode": "in_class"},
        headers={
            "cf-connecting-ip": CAMPUS_IP,
            "true-client-ip": CAMPUS_IP,
            "x-forwarded-for": f"{CAMPUS_IP}, 172.71.195.123, 10.226.90.65",
        },
    )
    assert cf.status_code == 200
    # A body field cannot claim an address either.
    body = client.post(f"/api/rooms/{room_id}/join", json={"entry_id": eid, "mode": "in_class", "ip": CAMPUS_IP}, headers={"x-forwarded-for": HOME_IP})
    assert body.status_code == 403


def test_cloudflared_on_loopback_may_supply_cf_connecting_ip():
    _app, client = make_client(peer="127.0.0.1")
    room_id, _ = open_room(client)
    eid = entry_id(client, room_id, "דנה לוי")
    response = client.post(f"/api/rooms/{room_id}/join", json={"entry_id": eid, "mode": "in_class"}, headers={"cf-connecting-ip": CAMPUS_IP})
    assert response.status_code == 200


def test_barcode_frame_is_lecturer_only_and_signed():
    _app, client = make_client()
    room_id, headers = open_room(client)
    assert client.get(f"/api/rooms/{room_id}/barcode").status_code == 401
    frame = client.get(f"/api/rooms/{room_id}/barcode", headers=headers).json()
    assert frame["code"].startswith("ZM1.") and frame["qr_hold_seconds"] == 2.0
    assert frame["qr_frame_seconds"] == 0.25 and frame["qr_flicker_hz"] == 20


def test_no_id_or_email_is_asked_at_entry():
    _app, client = make_client()
    room_id, _ = open_room(client)
    names = client.get(f"/api/rooms/{room_id}/roster/names").json()["names"]
    assert {n["display"] for n in names} == {"דנה לוי", "יוסי כהן", "עמית שמש"}
    assert set(names[0]) == {"id", "display"}
