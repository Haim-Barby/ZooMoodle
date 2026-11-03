from app.crypto_tokens import KeyManager, TokenService


def test_hkdf_is_stable_and_salt_separates_rooms():
    manager = KeyManager(b"lecturer-master")
    salt_a = b"s" * 16
    salt_b = b"t" * 16
    assert manager.derive_room_key(salt_a) == manager.derive_room_key(salt_a)
    assert manager.derive_room_key(salt_a) != manager.derive_room_key(salt_b)
    assert len(manager.derive_room_key(salt_a)) == 32


def test_token_round_trip_and_rejection():
    manager = KeyManager(b"lecturer-master")
    key = manager.derive_room_key(b"room-salt-value!")
    other = manager.derive_room_key(b"other-salt-value")
    service = TokenService(window_seconds=5, grace_windows=1)
    issued = service.issue(key, "room1", now=1_000, nonce=b"\x01\x02")
    fresh = service.verify(key, "room1", issued.code, now=1_002)
    assert fresh.ok and not fresh.late
    assert service.verify(other, "room1", issued.code, now=1_002).ok is False
    assert service.verify(key, "room2", issued.code, now=1_002).ok is False
    assert service.verify(key, "room1", "!!!!!!!!", now=1_002).reason == "malformed"


def test_previous_window_is_late_and_older_window_fails():
    key = KeyManager(b"lecturer-master").derive_room_key(b"room-salt-value!")
    service = TokenService(window_seconds=5, grace_windows=1)
    issued = service.issue(key, "room1", now=1_000, nonce=b"\x0a\x0b")
    late = service.verify(key, "room1", issued.code, now=1_005)
    assert late.ok and late.late and late.reason == "late"
    expired = service.verify(key, "room1", issued.code, now=1_010)
    assert expired.ok is False
    assert expired.reason == "mismatch"
