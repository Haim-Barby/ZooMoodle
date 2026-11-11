import pytest

from app.screen_qr import ScreenQrError, ScreenQrService

KEY = b"k" * 32


def _service(now):
    return ScreenQrService(clock=lambda: now)


def _codes(service, room="r1", first=100, count=9, step=1):
    return [service.issue_at(KEY, room, slot).code for slot in range(first, first + count * step, step)]


def test_live_two_second_sequence_passes():
    service = _service(100 * 0.25 + 9 * 0.25)
    frames = service.verify_sequence(KEY, "r1", _codes(service))
    assert len(frames) == 9


def test_each_code_lives_a_quarter_second_and_flickers_at_20hz():
    service = _service(1000.1)
    a = service.issue(KEY, "r1")
    b = service.issue(KEY, "r1", now=1000.2)
    c = service.issue(KEY, "r1", now=1000.3)
    assert a.code == b.code != c.code
    assert service.public_params()["qr_flicker_hz"] == 20


@pytest.mark.parametrize(
    "mutate,reason",
    [
        (lambda codes: [codes[0]] * 9, "qr_static"),
        (lambda codes: codes[:3], "qr_short"),
        (lambda codes: list(reversed(codes)), "qr_sequence"),
        (lambda codes: codes[:2] + codes[6:], "qr_sequence"),
    ],
)
def test_bad_sequences_are_rejected(mutate, reason):
    service = _service(100 * 0.25 + 9 * 0.25)
    with pytest.raises(ScreenQrError) as err:
        service.verify_sequence(KEY, "r1", mutate(_codes(service)))
    assert err.value.reason == reason


def test_stale_code_by_server_clock_is_rejected():
    service = _service(100 * 0.25 + 30)
    with pytest.raises(ScreenQrError) as err:
        service.verify_sequence(KEY, "r1", _codes(service))
    assert err.value.reason == "qr_stale"


def test_code_is_bound_to_its_room():
    service = _service(100 * 0.25 + 9 * 0.25)
    with pytest.raises(ScreenQrError) as err:
        service.verify_sequence(KEY, "other-room", _codes(service))
    assert err.value.reason == "qr_mismatch"
