"""Per-room keys (HKDF) and short-lived broadcast tokens (HMAC)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

HKDF_INFO = b"zoomoodle-room-v1"
NONCE_LEN = 2
MAC_LEN = 4


def b32encode(data: bytes) -> str:
    return base64.b32encode(data).decode("ascii").rstrip("=")


def b32decode(text: str) -> bytes:
    cleaned = "".join(text.split()).upper().rstrip("=")
    pad = "=" * ((8 - len(cleaned) % 8) % 8)
    return base64.b32decode(cleaned + pad, casefold=True)


class KeyManager:
    def __init__(self, master_secret: bytes):
        if not master_secret:
            raise ValueError("master secret is empty")
        self._master = master_secret

    def derive_room_key(self, room_salt: bytes) -> bytes:
        if len(room_salt) < 16:
            raise ValueError("room salt must be at least 16 bytes")
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=room_salt,
            info=HKDF_INFO,
        ).derive(self._master)


@dataclass(frozen=True)
class IssuedToken:
    code: str
    window: int
    nonce: bytes
    issued_at: float
    payload: bytes


@dataclass(frozen=True)
class TokenVerdict:
    ok: bool
    late: bool
    window: int | None
    reason: str


class TokenService:
    """Broadcast tokens are redeemable by every device that heard them.

    A whole class shares one acoustic signal, so "single-use" means once
    per device per code, not once for the entire room.
    """

    def __init__(self, window_seconds: int = 5, grace_windows: int = 1, clock=None):
        if window_seconds < 1:
            raise ValueError("window_seconds")
        self.window_seconds = window_seconds
        self.grace_windows = grace_windows
        self._clock = clock or time.time

    def now(self) -> float:
        return float(self._clock())

    def window_for(self, now: float | None = None) -> int:
        now = self.now() if now is None else now
        return int(now // self.window_seconds)

    def issue(
        self,
        room_key: bytes,
        room_id: str,
        now: float | None = None,
        nonce: bytes | None = None,
    ) -> IssuedToken:
        now = self.now() if now is None else now
        window = int(now // self.window_seconds)
        nonce = os.urandom(NONCE_LEN) if nonce is None else nonce
        if len(nonce) != NONCE_LEN:
            raise ValueError("nonce length")
        payload = nonce + self._mac(room_key, room_id, window, nonce)
        return IssuedToken(
            code=b32encode(payload),
            window=window,
            nonce=nonce,
            issued_at=now,
            payload=payload,
        )

    def verify(self, room_key: bytes, room_id: str, code: str, now: float | None = None) -> TokenVerdict:
        now = self.now() if now is None else now
        try:
            payload = b32decode(code)
        except Exception:
            return TokenVerdict(False, False, None, "malformed")
        if len(payload) != NONCE_LEN + MAC_LEN:
            return TokenVerdict(False, False, None, "malformed")
        nonce, mac = payload[:NONCE_LEN], payload[NONCE_LEN:]
        current = int(now // self.window_seconds)
        for age in range(self.grace_windows + 1):
            window = current - age
            expected = self._mac(room_key, room_id, window, nonce)
            if hmac.compare_digest(mac, expected):
                late = age > 0
                return TokenVerdict(True, late, window, "late" if late else "ok")
        return TokenVerdict(False, False, None, "mismatch")

    def _mac(self, room_key: bytes, room_id: str, window: int, nonce: bytes) -> bytes:
        message = f"{room_id}|{window}|".encode("utf-8") + nonce
        return hmac.new(room_key, message, hashlib.sha256).digest()[:MAC_LEN]
