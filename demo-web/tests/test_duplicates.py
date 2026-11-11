from app.config import Settings
from app.mailer import Mailer
from tests.conftest import (
    HOME_IP,
    ROSTER,
    check_in_class,
    entry_id,
    join,
    make_client,
    make_settings,
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


def test_same_name_again_sends_an_email_code_and_the_right_code_wins():
    app, client = make_client()
    room_id, headers = open_room(client)
    a, b = _two_in_class_same_name(app, client, room_id)
    _repick(client, room_id, a, "דנה לוי")
    stage = _repick(client, room_id, b, "דנה לוי").json()
    assert stage["state"] == "email_code"
    assert _me(client, room_id, a)["state"] == "email_code"
    conflict = _dash(client, room_id, headers)["conflicts"][0]
    # No SMTP in tests: demo mode shows the code to the lecturer only.
    assert conflict["email"]["demo_label"] == "מצב הדגמה – המייל לא נשלח"
    code = conflict["email"]["demo_code"]
    assert len(code) == 6 and code.isdigit()
    assert code not in signed(client, a, "GET", f"/api/rooms/{room_id}/me").text
    wrong = "000000" if code != "000000" else "111111"
    assert signed(client, b, "POST", f"/api/rooms/{room_id}/email-code", {"code": wrong}).status_code == 401
    ok = signed(client, client_creds := a, "POST", f"/api/rooms/{room_id}/email-code", {"code": code})
    assert ok.status_code == 200 and ok.json()["state"] == "present"
    assert _me(client, room_id, b)["state"] == "lecturer_decision"
    # Single use.
    again = signed(client, client_creds, "POST", f"/api/rooms/{room_id}/email-code", {"code": code})
    assert again.status_code == 409
    assert "demo_code" not in (_dash(client, room_id, headers)["conflicts"][0]["email"] or {})


def test_code_attempts_are_limited_then_the_lecturer_decides():
    app, client = make_client()
    room_id, headers = open_room(client)
    a, b = _two_in_class_same_name(app, client, room_id)
    _repick(client, room_id, a, "דנה לוי")
    _repick(client, room_id, b, "דנה לוי")
    code = _dash(client, room_id, headers)["conflicts"][0]["email"]["demo_code"]
    wrong = "000000" if code != "000000" else "111111"
    for creds in (a, b):
        for _ in range(3):
            signed(client, creds, "POST", f"/api/rooms/{room_id}/email-code", {"code": wrong})
    assert _me(client, room_id, a)["state"] == "lecturer_decision"
    late = signed(client, a, "POST", f"/api/rooms/{room_id}/email-code", {"code": code})
    assert late.status_code in (409, 429)
    # Lecturer asks in class and gives the name to B.
    conflict = _dash(client, room_id, headers)["conflicts"][0]
    claim_b = _me(client, room_id, b)["claim_id"]
    assert {c["claim_id"] for c in conflict["claims"]} >= {claim_b}
    decided = client.post(f"/api/rooms/{room_id}/conflicts/decide", json={"claim_id": claim_b, "action": "accept"}, headers=headers)
    assert decided.json()["state"] == "present"
    assert _me(client, room_id, a)["state"] == "rejected"
    dash = _dash(client, room_id, headers)
    assert dash["counts"]["in_class"] == 1 and dash["conflicts"] == []


def test_code_expiry_hands_the_case_to_the_lecturer():
    app, client = make_client()
    room_id, headers = open_room(client)
    a, b = _two_in_class_same_name(app, client, room_id)
    _repick(client, room_id, a, "דנה לוי")
    _repick(client, room_id, b, "דנה לוי")
    book = app.state.store.get(room_id).checkin
    for challenge in book.challenges.values():
        challenge.expires_at = 0
    assert _me(client, room_id, a)["state"] == "lecturer_decision"
    assert _me(client, room_id, b)["state"] == "lecturer_decision"


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


class FakeSMTP:
    sent = []

    def __init__(self, host, port):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        self.user = user

    def send_message(self, message):
        FakeSMTP.sent.append(message)


def test_smtp_mode_sends_to_the_demo_override_and_hides_the_code():
    FakeSMTP.sent = []
    settings = make_settings(
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_user="bot@example.test",
        smtp_password="app-password",
        smtp_from="bot@example.test",
        demo_email_override="demo-inbox@example.test",
    )
    mailer = Mailer(settings, smtp_factory=FakeSMTP)
    app, client = make_client(settings, mailer=mailer)
    room_id, headers = open_room(client)
    a, b = _two_in_class_same_name(app, client, room_id)
    _repick(client, room_id, a, "דנה לוי")
    _repick(client, room_id, b, "דנה לוי")
    assert len(FakeSMTP.sent) == 1
    message = FakeSMTP.sent[0]
    assert message["To"] == "demo-inbox@example.test"
    body = message.get_content()
    code = next(token for token in body.split() if token.isdigit() and len(token) == 6)
    conflict = _dash(client, room_id, headers)["conflicts"][0]
    assert conflict["email"]["sent"] is True and "demo_code" not in conflict["email"]
    assert _me(client, room_id, b)["email_sent"] is True
    ok = signed(client, b, "POST", f"/api/rooms/{room_id}/email-code", {"code": code})
    assert ok.json()["state"] == "present"


def test_without_override_the_code_goes_to_the_roster_address():
    FakeSMTP.sent = []
    settings = make_settings(smtp_host="smtp.example.test", smtp_from="bot@example.test")
    app, client = make_client(settings, mailer=Mailer(settings, smtp_factory=FakeSMTP))
    room_id, _ = open_room(client)
    a, b = _two_in_class_same_name(app, client, room_id)
    _repick(client, room_id, a, "דנה לוי")
    _repick(client, room_id, b, "דנה לוי")
    assert FakeSMTP.sent[0]["To"] == "dana@example.test"
