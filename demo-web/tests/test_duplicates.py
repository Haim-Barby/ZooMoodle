from tests.conftest import (
    HOME_IP,
    ROSTER,
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


def test_same_name_after_a_repick_goes_to_the_lecturer():
    app, client = make_client()
    room_id, headers = open_room(client)
    a, b = _two_in_class_same_name(app, client, room_id)
    _repick(client, room_id, a, "דנה לוי")
    stage = _repick(client, room_id, b, "דנה לוי").json()
    assert stage["state"] == "lecturer_decision"
    assert _me(client, room_id, a)["state"] == "lecturer_decision"
    dash = _dash(client, room_id, headers)
    assert dash["counts"]["conflicts"] == 2 and dash["counts"]["in_class"] == 0
    conflict = dash["conflicts"][0]
    assert conflict["name"] == "דנה לוי" and set(conflict) == {"name", "claims"}
    # Lecturer asks in class and gives the name to B.
    claim_b = _me(client, room_id, b)["claim_id"]
    decided = client.post(f"/api/rooms/{room_id}/conflicts/decide", json={"claim_id": claim_b, "action": "accept"}, headers=headers)
    assert decided.json()["state"] == "present"
    assert _me(client, room_id, a)["state"] == "rejected"
    dash = _dash(client, room_id, headers)
    assert dash["counts"]["in_class"] == 1 and dash["conflicts"] == []


def test_a_third_phone_on_a_decided_name_goes_to_the_lecturer():
    app, client = make_client()
    room_id, headers = open_room(client)
    a, b = _two_in_class_same_name(app, client, room_id)
    _repick(client, room_id, a, "דנה לוי")
    _repick(client, room_id, b, "דנה לוי")
    client.post(f"/api/rooms/{room_id}/conflicts/decide", json={"claim_id": a["claim_id"], "action": "accept"}, headers=headers)
    c = check_in_class(app, client, room_id, "דנה לוי")
    assert _me(client, room_id, c)["state"] == "repick"
    assert _me(client, room_id, a)["state"] == "present"


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
