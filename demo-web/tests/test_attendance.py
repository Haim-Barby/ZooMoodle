from app.attendance import AttendanceService, CheckInError
from app.crypto_tokens import KeyManager, TokenService
from tests.conftest import make_device


def _service(now=1_000):
    tokens = TokenService(window_seconds=5, grace_windows=1, clock=lambda: now)
    return AttendanceService(tokens, max_challenge_age=8), tokens


def _room_key():
    return KeyManager(b"lecturer-master").derive_room_key(b"room-salt-value!")


def _check(service, device, mode, code, zone, subnet, when, name="Ada"):
    challenge = service.open_challenge("s1", device["device_id"], device["jwk"], when)
    return service.check_in(
        challenge_id=challenge.id,
        signature=device["sign"](challenge.id, challenge.nonce),
        mode=mode,
        token_code=code,
        seat_zone=zone,
        subnet=subnet,
        room_key=_room_key(),
        room_id="room1",
        student_name=name,
        now=when,
    )


def test_two_devices_can_redeem_one_broadcast_and_one_device_cannot_reuse_it():
    service, tokens = _service(1_000)
    key = _room_key()
    issued = tokens.issue(key, "room1", now=1_000, nonce=b"\x01\x02")
    phone_a = make_device()
    phone_b = make_device()
    first = _check(service, phone_a, "in_class", issued.code, "front-left", "match", 1_001)
    second = service.open_challenge("s2", phone_b["device_id"], phone_b["jwk"], 1_001)
    other = service.check_in(
        challenge_id=second.id,
        signature=phone_b["sign"](second.id, second.nonce),
        mode="in_class",
        token_code=issued.code,
        seat_zone="back-right",
        subnet="match",
        room_key=key,
        room_id="room1",
        student_name="Bea",
        now=1_001,
    )
    assert first.record.confidence == "high"
    assert other.record.confidence == "high"
    again = service.open_challenge("s1", phone_a["device_id"], phone_a["jwk"], 1_002)
    try:
        service.check_in(
            challenge_id=again.id,
            signature=phone_a["sign"](again.id, again.nonce),
            mode="in_class",
            token_code=issued.code,
            seat_zone="front-left",
            subnet="match",
            room_key=key,
            room_id="room1",
            student_name="Ada",
            now=1_002,
        )
        raise AssertionError("reused token should fail")
    except CheckInError as exc:
        assert exc.reason == "reused_token"


def test_bad_signature_and_expired_challenge_are_rejected():
    service, _tokens = _service(1_000)
    device = make_device()
    challenge = service.open_challenge("s1", device["device_id"], device["jwk"], 1_000)
    try:
        service.check_in(
            challenge_id=challenge.id,
            signature=b"\x00" * 64,
            mode="in_class",
            token_code="AAAA",
            seat_zone="front-left",
            subnet="match",
            room_key=_room_key(),
            room_id="room1",
            student_name="Ada",
            now=1_001,
        )
        raise AssertionError("bad signature should fail")
    except CheckInError as exc:
        assert exc.reason == "bad_signature"
    assert challenge.used is False
    try:
        service.check_in(
            challenge_id=challenge.id,
            signature=device["sign"](challenge.id, challenge.nonce),
            mode="remote",
            token_code=None,
            seat_zone="front-left",
            subnet="not_applicable",
            room_key=_room_key(),
            room_id="room1",
            student_name="Ada",
            now=1_009,
        )
        raise AssertionError("expired challenge should fail")
    except CheckInError as exc:
        assert exc.reason == "challenge_expired"


def test_late_token_remote_and_anomalies():
    service, tokens = _service(1_000)
    key = _room_key()
    issued = tokens.issue(key, "room1", now=1_000, nonce=b"\x0a\x0b")
    phone = make_device()
    # Move the clock by using explicit timestamps. The token window at 1000 is
    # previous once we check in at 1005.
    late = _check(service, phone, "in_class", issued.code, "middle-left", "mismatch", 1_005)
    assert late.record.token_late is True
    assert "late_token" in late.record.flags
    assert "subnet_mismatch" in late.record.flags
    assert late.record.confidence == "low"

    remote = _check(service, phone, "remote", None, "middle-left", "not_applicable", 1_006)
    assert remote.record.mode == "remote"
    assert remote.record.external_token
    assert "both_modes" in remote.record.flags
    assert "both_modes" in service.records[0].flags

    other = make_device()
    other_challenge = service.open_challenge("s2", phone["device_id"], phone["jwk"], 1_006)
    shared = service.check_in(
        challenge_id=other_challenge.id,
        signature=phone["sign"](other_challenge.id, other_challenge.nonce),
        mode="remote",
        token_code=None,
        seat_zone="back-left",
        subnet="not_applicable",
        room_key=key,
        room_id="room1",
        student_name="Bea",
        now=1_006,
    )
    assert "shared_device" in shared.record.flags

    third = service.open_challenge("s1", other["device_id"], other["jwk"], 1_007)
    multi = service.check_in(
        challenge_id=third.id,
        signature=other["sign"](third.id, third.nonce),
        mode="remote",
        token_code=None,
        seat_zone="back-right",
        subnet="not_applicable",
        room_key=key,
        room_id="room1",
        student_name="Ada",
        now=1_007,
    )
    assert "multi_device" in multi.record.flags
