"""Flickering screen barcode for in-class presence.

The lecturer screen shows a video-like QR: the signed payload in the
centre changes about every 250 milliseconds, and a border around it
shimmers many times a second. A student must keep the camera on that
live pattern for about two seconds. The server, not the phone clock,
checks each decoded frame for freshness when it arrives, and also
checks that the frames actually changed over those two seconds. A
checkmark still needs the local network verifier as well.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import math
import os
import time
from dataclasses import dataclass

FRAME_SECONDS = 0.25
MAX_AGE_SECONDS = 6.0
HOLD_SECONDS = 2.0
MIN_DISTINCT = 5
MAX_GAP_SLOTS = 3
FLICKER_HZ = 20
NONCE_LEN = 8
MAC_LEN = 16
PREFIX = "ZM1."
DOMAIN = b"zoomoodle-screen-qr-v1"
FLICKER_DOMAIN = b"zoomoodle-flicker-v1"


class ScreenQrError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class IssuedFrame:
    code: str
    slot: int
    issued_at: float
    expires_in: float
    token_id: str


@dataclass(frozen=True)
class VerifiedFrame:
    slot: int
    token_id: str
    age: float
    issued_at: float


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    cleaned = "".join((text or "").split())
    pad = "=" * ((4 - len(cleaned) % 4) % 4)
    return base64.urlsafe_b64decode(cleaned + pad)


def _token_id(slot: int, nonce: bytes) -> str:
    return _b64url(slot.to_bytes(8, "big") + nonce)


class ScreenQrService:
    def __init__(
        self,
        frame_seconds: float = FRAME_SECONDS,
        max_age_seconds: float = MAX_AGE_SECONDS,
        hold_seconds: float = HOLD_SECONDS,
        min_distinct: int = MIN_DISTINCT,
        max_gap_slots: int = MAX_GAP_SLOTS,
        flicker_hz: int = FLICKER_HZ,
        clock=None,
        sequence_length: int | None = None,
    ):
        if frame_seconds <= 0 or max_age_seconds <= 0 or hold_seconds <= 0:
            raise ValueError("frame, max age and hold must be positive")
        if sequence_length is not None:
            min_distinct = sequence_length
        if min_distinct < 2:
            raise ValueError("min_distinct")
        if max_gap_slots < 1:
            raise ValueError("max_gap_slots")
        if flicker_hz < 1:
            raise ValueError("flicker_hz")
        self.frame_seconds = float(frame_seconds)
        self.max_age_seconds = float(max_age_seconds)
        self.hold_seconds = float(hold_seconds)
        self.min_distinct = int(min_distinct)
        self.max_gap_slots = int(max_gap_slots)
        self.flicker_hz = int(flicker_hz)
        self._clock = clock or time.time
        self._current: tuple[str, int, bytes] | None = None

    @property
    def sequence_length(self) -> int:
        return self.min_distinct

    @property
    def slot_span(self) -> int:
        return max(
            self.min_distinct,
            int(math.ceil(self.hold_seconds / self.frame_seconds - 1e-12)),
        )

    def now(self) -> float:
        return float(self._clock())

    def public_params(self) -> dict:
        return {
            "qr_frame_seconds": self.frame_seconds,
            "qr_max_age_seconds": self.max_age_seconds,
            "qr_hold_seconds": self.hold_seconds,
            "qr_min_distinct": self.min_distinct,
            "qr_needed": self.min_distinct,
            "qr_flicker_hz": self.flicker_hz,
        }

    def flicker_seed(self, room_key: bytes, room_id: str) -> str:
        if not room_key:
            raise ScreenQrError("qr_mismatch")
        message = FLICKER_DOMAIN + b"|" + str(room_id).encode("utf-8")
        return hmac.new(room_key, message, hashlib.sha256).hexdigest()[:16]

    def slot_for(self, now: float | None = None) -> int:
        now = self.now() if now is None else now
        return int(now // self.frame_seconds)

    def coverage_seconds(self, frames: list[VerifiedFrame]) -> float:
        if not frames:
            return 0.0
        return (frames[-1].slot - frames[0].slot + 1) * self.frame_seconds

    def issue(self, room_key: bytes, room_id: str, now: float | None = None) -> IssuedFrame:
        now = self.now() if now is None else now
        slot = self.slot_for(now)
        if self._current and self._current[0] == room_id and self._current[1] == slot:
            nonce = self._current[2]
        else:
            nonce = os.urandom(NONCE_LEN)
            self._current = (room_id, slot, nonce)
        return self.issue_at(room_key, room_id, slot, nonce=nonce, now=now)

    def issue_at(
        self,
        room_key: bytes,
        room_id: str,
        slot: int,
        nonce: bytes | None = None,
        now: float | None = None,
    ) -> IssuedFrame:
        now = self.now() if now is None else now
        if slot < 0:
            raise ScreenQrError("qr_mismatch")
        nonce = os.urandom(NONCE_LEN) if nonce is None else nonce
        if len(nonce) != NONCE_LEN:
            raise ValueError("nonce length")
        issued_at = slot * self.frame_seconds
        expires_in = max(0.0, issued_at + self.frame_seconds - now)
        mac = self._mac(room_key, room_id, slot, nonce)
        payload = slot.to_bytes(8, "big") + nonce + mac
        return IssuedFrame(
            code=PREFIX + _b64url(payload),
            slot=slot,
            issued_at=issued_at,
            expires_in=expires_in,
            token_id=_token_id(slot, nonce),
        )

    def verify_one(self, room_key: bytes, room_id: str, code: str, now: float | None = None) -> VerifiedFrame:
        now = self.now() if now is None else now
        slot, nonce = self._decode(room_key, room_id, code)
        issued_at = slot * self.frame_seconds
        age = now - issued_at
        if age < -0.5:
            raise ScreenQrError("qr_mismatch")
        if age > self.max_age_seconds:
            raise ScreenQrError("qr_stale")
        return VerifiedFrame(
            slot=slot,
            token_id=_token_id(slot, nonce),
            age=age,
            issued_at=issued_at,
        )

    def verify_sequence(
        self,
        room_key: bytes,
        room_id: str,
        codes: list[str],
        now: float | None = None,
    ) -> list[VerifiedFrame]:
        now = self.now() if now is None else now
        if not isinstance(codes, list) or not codes:
            raise ScreenQrError("qr_sequence")
        seen_ids: set[str] = set()
        frames: list[VerifiedFrame] = []
        for raw in codes:
            if not isinstance(raw, str) or not raw.strip():
                raise ScreenQrError("qr_sequence")
            frame = self.verify_one(room_key, room_id, raw, now)
            if frame.token_id in seen_ids:
                raise ScreenQrError("qr_static")
            seen_ids.add(frame.token_id)
            if frames and frame.slot <= frames[-1].slot:
                raise ScreenQrError("qr_sequence")
            if frames and frame.slot - frames[-1].slot > self.max_gap_slots:
                raise ScreenQrError("qr_sequence")
            frames.append(frame)
        if len(frames) == 1 or len({frame.slot for frame in frames}) == 1:
            raise ScreenQrError("qr_static")
        if len(frames) < self.min_distinct or self.coverage_seconds(frames) + 1e-9 < self.hold_seconds:
            raise ScreenQrError("qr_short")
        return frames

    def _decode(self, room_key: bytes, room_id: str, code: str) -> tuple[int, bytes]:
        text = (code or "").strip()
        if not text.startswith(PREFIX):
            raise ScreenQrError("qr_mismatch")
        try:
            payload = _b64url_decode(text[len(PREFIX):])
        except Exception as exc:
            raise ScreenQrError("qr_mismatch") from exc
        if len(payload) != 8 + NONCE_LEN + MAC_LEN:
            raise ScreenQrError("qr_mismatch")
        slot = int.from_bytes(payload[:8], "big")
        nonce = payload[8:8 + NONCE_LEN]
        mac = payload[8 + NONCE_LEN:]
        expected = self._mac(room_key, room_id, slot, nonce)
        if not hmac.compare_digest(mac, expected):
            raise ScreenQrError("qr_mismatch")
        return slot, nonce

    def _mac(self, room_key: bytes, room_id: str, slot: int, nonce: bytes) -> bytes:
        if not room_key:
            raise ScreenQrError("qr_mismatch")
        message = DOMAIN + b"|" + str(room_id).encode("utf-8") + b"|" + slot.to_bytes(8, "big") + nonce
        return hmac.new(room_key, message, hashlib.sha256).digest()[:MAC_LEN]
