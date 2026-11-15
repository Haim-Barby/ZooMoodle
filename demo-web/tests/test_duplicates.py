from tests.conftest import (
    HOME_IP,
    check_in_class,
    entry_id,
    join,
    make_client,
    open_room,
    signed,
)


def _dash(client, room_id, headers):
    return client.get(f"/api/rooms/{room_id}/dashboard", headers=headers).json()


def _me(client, room_id, creds):
    return signed(client, creds, "GET", f"/api/rooms/{room_id}/me").json()


def _two_in_class_same_name(app, client, room_id):
    a = check_in_class(app, client, room_id, "דנה לוי", zone="front-left")
    b = check_in_class(app, client, room_id, "דנה לוי", zone="back-right")
    return a, b


def _repick(client, room_id, creds, display):
    eid = entry_id(client, room_id, display)
    return signed(client, creds, "POST", f"/api/rooms/{room_id}/repick", {"entry_id": eid})


def test_in_class_beats_remote_and_remote_is_flagged():
    app, client = make_client()
    room_id, headers = open_room(client)
    remote = join(client, room_id, "דנה לוי", "remote", ip=HOME_IP).json()
    assert remote["state"] == "remote"
    check_in_class(app, client, room_id, "דנה לוי")
    assert _me(client, room_id, remote)["state"] == "flagged_remote"
    dash = _dash(client, room_id, headers)
    assert dash["counts"] == {"in_class": 1, "remote": 0, "pending": 0, "conflicts": 1}
    assert dash["conflicts"][0]["name"] == "דנה לוי"
    # Later remote picks of a verified name are flagged at once.
    late = join(client, room_id, "דנה לוי", "remote", ip=HOME_IP).json()
    assert late["state"] == "flagged_remote" and not late["checked"]
    # A flagged student cannot write notes until the lecturer decides.
    note = signed(client, late, "POST", f"/api/rooms/{room_id}/comments", {"text": "hi"})
    assert note.status_code == 403


def test_two_in_class_with_one_name_get_a_repick_popup_and_can_resolve():
    app, client = make_client()
    room_id, headers = open_room(client)
    a, b = _two_in_class_same_name(app, client, room_id)
    assert _me(client, room_id, a)["state"] == "repick"
    assert _me(client, room_id, b)["state"] == "repick"
    assert _dash(client, room_id, headers)["counts"]["in_class"] == 0
    # B really is Yossi; A really is Dana.
    assert _repick(client, room_id, b, "יוסי כהן").json()["state"] == "present"
    done = _repick(client, room_id, a, "דנה לוי").json()
    assert done["state"] == "present" and done["welcome"] == "ברוך הבא דנה לוי"
    dash = _dash(client, room_id, headers)
    assert dash["counts"]["in_class"] == 2 and dash["conflicts"] == []


def _to_lecturer_code(app, client, room_id, headers):
    a, b = _two_in_class_same_name(app, client, room_id)
    _repick(client, room_id, a, "דנה לוי")
    stage = _repick(client, room_id, b, "דנה לוי").json()
    assert stage["state"] == "lecturer_code"
    code = _dash(client, room_id, headers)["conflicts"][0]["lecturer_code"]["code"]
    return a, b, code


def _code(client, room_id, creds, code):
    return signed(client, creds, "POST", f"/api/rooms/{room_id}/name-code", {"code": code})


def _wrong(code):
    return "000000" if code != "000000" else "111111"


def test_same_name_again_shows_a_lecturer_code_that_gives_the_name_to_the_right_phone():
    app, client = make_client()
    room_id, headers = open_room(client)
    a, b, code = _to_lecturer_code(app, client, room_id, headers)
    assert _me(client, room_id, a)["state"] == "lecturer_code"
    conflict = _dash(client, room_id, headers)["conflicts"][0]
    assert len(code) == 6 and code.isdigit()
    assert conflict["lecturer_code"]["devices"] == 2 and conflict["lecturer_code"]["expires_in"] > 0
    # The code is on the lecturer dashboard only, never in a student response.
    assert code not in signed(client, a, "GET", f"/api/rooms/{room_id}/me").text
    assert code not in signed(client, b, "GET", f"/api/rooms/{room_id}/me").text
    # A wrong code is refused.
    assert _code(client, room_id, b, _wrong(code)).status_code == 401
    # The lecturer types the code on A's phone: A gets the name, B is removed from it.
    ok = _code(client, room_id, a, code)
    assert ok.status_code == 200 and ok.json()["state"] == "present"
    assert ok.json()["welcome"] == "ברוך הבא דנה לוי"
    assert _me(client, room_id, b)["state"] == "rejected"
    dash = _dash(client, room_id, headers)
    assert dash["counts"]["in_class"] == 1 and dash["counts"]["conflicts"] == 0
    assert code not in str(dash)


def test_the_code_is_single_use():
    app, client = make_client()
    room_id, headers = open_room(client)
    a, b, code = _to_lecturer_code(app, client, room_id, headers)
    assert _code(client, room_id, a, code).status_code == 200
    assert _code(client, room_id, a, code).status_code == 409
    assert _code(client, room_id, b, code).status_code == 409
    assert _me(client, room_id, b)["state"] == "rejected"


def test_the_removed_phone_can_check_in_again_with_another_name():
    app, client = make_client()
    room_id, headers = open_room(client)
    a, b, code = _to_lecturer_code(app, client, room_id, headers)
    _code(client, room_id, a, code)
    assert _me(client, room_id, b)["state"] == "rejected"
    # "Start over" on phone B: a new check-in with the student's own name.
    again = check_in_class(app, client, room_id, "יוסי כהן")
    assert _me(client, room_id, again)["state"] == "present"
    assert _dash(client, room_id, headers)["counts"]["in_class"] == 2


def test_wrong_tries_are_limited_per_phone_and_renew_the_code():
    app, client = make_client()
    room_id, headers = open_room(client)
    a, b, code = _to_lecturer_code(app, client, room_id, headers)
    wrong = _wrong(code)
    for _ in range(3):
        assert _code(client, room_id, b, wrong).status_code == 401
    assert _code(client, room_id, b, code).status_code == 429
    for _ in range(3):
        assert _code(client, room_id, a, wrong).status_code == 401
    # Six wrong tries in total: a fresh code is shown to the lecturer; both phones still wait.
    fresh = _dash(client, room_id, headers)["conflicts"][0]["lecturer_code"]["code"]
    assert _me(client, room_id, a)["state"] == "lecturer_code"
    assert _me(client, room_id, b)["state"] == "lecturer_code"
    if fresh != code:
        assert _code(client, room_id, a, code).status_code == 401
    assert _code(client, room_id, a, fresh).json()["state"] == "present"


def test_an_expired_code_renews_and_the_phones_keep_waiting():
    app, client = make_client()
    room_id, headers = open_room(client)
    a, b, code = _to_lecturer_code(app, client, room_id, headers)
    book = app.state.store.get(room_id).checkin
    for challenge in book.challenges.values():
        challenge.expires_at = 0
    assert _me(client, room_id, a)["state"] == "lecturer_code"
    assert _me(client, room_id, b)["state"] == "lecturer_code"
    view = _dash(client, room_id, headers)["conflicts"][0]["lecturer_code"]
    assert view["expires_in"] > 0
    if view["code"] != code:
        assert _code(client, room_id, b, code).status_code == 401
    assert _code(client, room_id, b, view["code"]).json()["state"] == "present"
    assert _me(client, room_id, a)["state"] == "rejected"


def test_a_phone_that_repicks_a_name_given_by_the_lecturer_is_rejected():
    app, client = make_client()
    room_id, headers = open_room(client)
    a, b, code = _to_lecturer_code(app, client, room_id, headers)
    _code(client, room_id, a, code)
    c = check_in_class(app, client, room_id, "דנה לוי")
    assert _me(client, room_id, c)["state"] == "repick"
    assert _repick(client, room_id, c, "דנה לוי").json()["state"] == "rejected"
    assert _me(client, room_id, a)["state"] == "present"


def test_lecturer_accept_on_the_dashboard_also_closes_the_code():
    app, client = make_client()
    room_id, headers = open_room(client)
    a, b, code = _to_lecturer_code(app, client, room_id, headers)
    client.post(f"/api/rooms/{room_id}/conflicts/decide", json={"claim_id": b["claim_id"], "action": "accept"}, headers=headers)
    assert _me(client, room_id, b)["state"] == "present"
    assert _me(client, room_id, a)["state"] == "rejected"
    assert _code(client, room_id, a, code).status_code == 409
    assert _dash(client, room_id, headers)["conflicts"] == []


def test_lecturer_can_accept_a_flagged_remote_or_reject_it():
    app, client = make_client()
    room_id, headers = open_room(client)
    first = join(client, room_id, "עמית שמש", "remote", ip=HOME_IP).json()
    second = join(client, room_id, "עמית שמש", "remote", ip=HOME_IP).json()
    assert _me(client, room_id, first)["state"] == "flagged_remote"
    assert _me(client, room_id, second)["state"] == "flagged_remote"
    client.post(f"/api/rooms/{room_id}/conflicts/decide", json={"claim_id": first["claim_id"], "action": "accept"}, headers=headers)
    assert _me(client, room_id, first)["state"] == "remote"
    assert _me(client, room_id, second)["state"] == "rejected"
    assert client.post(f"/api/rooms/{room_id}/conflicts/decide", json={"claim_id": first["claim_id"], "action": "x"}, headers=headers).status_code == 400
    assert client.post(f"/api/rooms/{room_id}/conflicts/decide", json={"claim_id": first["claim_id"], "action": "reject"}).status_code == 401
