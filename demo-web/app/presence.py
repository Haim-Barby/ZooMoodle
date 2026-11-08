"""Hotspot presence challenges.

A checkmark requires a paired helper to observe the challenge from its bound
interface, then the same student session to finish it. A claimed IP or SSID
is not evidence. Closing the room drops unfinished challenges.
"""

from __future__ import annotations

import hmac
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.session_keys import canonical_message, encode_secret

HELPER_SALT = b"zoomoodle-helper-v1"
HELPER_INFO = b"zoomoodle-helper-mac"
CHALLENGE_TTL_SECONDS = 90


class PresenceError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def derive_helper_verifier(secret: bytes) -> bytes:
    if len(secret) < 32:
        raise ValueError("helper secret must be 32 bytes")
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=HELPER_SALT,
        info=HELPER_INFO,
    ).derive(secret)


def _b64_mac(verifier: bytes, message: bytes) -> str:
    from app.session_keys import sign_message

    return sign_message(verifier, message)


def _decode_mac(text: str) -> bytes:
    from app.session_keys import _b64u_decode

    try:
        return _b64u_decode(text)
    except Exception as exc:
        raise PresenceError("bad_helper") from exc


@dataclass
class Challenge:
    id: str
    room_id: str
    entry_id: str
    session_id: str
    expires_at: float
    observed: bool = False
    used: bool = False


class PresenceBook:
    def __init__(self, clock=None, ttl: float = CHALLENGE_TTL_SECONDS):
        self._clock = clock or time.time
        self.ttl = ttl
        self.helper_id = ""
        self.helper_verifier = b""
        self.bind_url = ""
        self.challenges: dict[str, Challenge] = {}
        self.in_class: dict[str, bool] = {}
        self.remote: dict[str, bool] = {}
        self._helper_nonces: dict[str, float] = {}
        self.closed = False

    def now(self) -> float:
        return float(self._clock())

    def pair(self) -> tuple[str, str]:
        secret = os.urandom(32)
        self.helper_id = secrets.token_hex(8)
        self.helper_verifier = derive_helper_verifier(secret)
        token = encode_secret(secret)
        del secret
        return self.helper_id, token

    def revoke_helper(self) -> None:
        self.helper_id = ""
        self.helper_verifier = b""
        self._helper_nonces.clear()

    def set_bind_url(self, url: str) -> str:
        text = (url or "").strip()
        if not text.startswith("http://") or "://" not in text[4:]:
            raise PresenceError("bad_bind_url")
        rest = text[len("http://") :]
        if "@" in rest or rest.startswith("/") or not rest:
            raise PresenceError("bad_bind_url")
        self.bind_url = text.rstrip("/")
        return self.bind_url

    def public_status(self) -> dict:
        return {
            "helper_paired": bool(self.helper_id and self.helper_verifier),
            "bind_url": self.bind_url,
        }

    def issue(self, room_id: str, entry_id: str, session_id: str) -> Challenge:
        if self.closed:
            raise PresenceError("presence_closed")
        if not self.helper_verifier or not self.bind_url:
            raise PresenceError("presence_unavailable")
        now = self.now()
        challenge = Challenge(
            id=secrets.token_hex(16),
            room_id=room_id,
            entry_id=entry_id,
            session_id=session_id,
            expires_at=now + self.ttl,
        )
        self.challenges[challenge.id] = challenge
        return challenge

    def observe(self, room_id: str, raw: bytes, message: bytes, signature: str, nonce: str, timestamp: str) -> None:
        if self.closed:
            raise PresenceError("presence_closed")
        self._verify_helper(message, signature, nonce, timestamp)
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except Exception as exc:
            raise PresenceError("bad_helper") from exc
        if not isinstance(body, dict):
            raise PresenceError("bad_helper")
        challenge_id = str(body.get("challenge_id") or "")
        challenge = self.challenges.get(challenge_id or "")
        if challenge is None or challenge.room_id != room_id:
            raise PresenceError("unknown_challenge")
        if challenge.used:
            raise PresenceError("presence_replay")
        if self.now() > challenge.expires_at:
            raise PresenceError("presence_expired")
        challenge.observed = True

    def finish(self, room_id: str, session_id: str, entry_id: str, challenge_id: str) -> Challenge:
        if self.closed:
            raise PresenceError("presence_closed")
        challenge = self.challenges.get(challenge_id or "")
        if challenge is None or challenge.room_id != room_id:
            raise PresenceError("unknown_challenge")
        if challenge.used:
            raise PresenceError("presence_replay")
        if self.now() > challenge.expires_at:
            raise PresenceError("presence_expired")
        if challenge.session_id != session_id or challenge.entry_id != entry_id:
            raise PresenceError("presence_mismatch")
        if not challenge.observed:
            raise PresenceError("presence_required")
        challenge.used = True
        self.in_class[entry_id] = True
        return challenge

    def mark_remote(self, entry_id: str) -> None:
        if entry_id:
            self.remote[entry_id] = True

    def close(self) -> None:
        self.closed = True
        self.challenges.clear()
        self.revoke_helper()

    def _verify_helper(self, message: bytes, signature: str, nonce: str, timestamp: str) -> None:
        if not self.helper_verifier:
            raise PresenceError("bad_helper")
        try:
            stamp = int(str(timestamp).strip())
        except (TypeError, ValueError):
            raise PresenceError("session_expired") from None
        if abs(self.now() - stamp) > 60:
            raise PresenceError("session_expired")
        nonce = (nonce or "").strip()
        if len(nonce) < 8 or nonce in self._helper_nonces:
            raise PresenceError("session_replay" if nonce in self._helper_nonces else "bad_helper")
        presented = _decode_mac(signature or "")
        expected = hmac.new(self.helper_verifier, message, hashlib.sha256).digest()
        if len(presented) != len(expected) or not hmac.compare_digest(presented, expected):
            raise PresenceError("bad_helper")
        self._helper_nonces[nonce] = stamp


def helper_message(method: str, target: str, body: bytes, timestamp: str, nonce: str) -> bytes:
    return canonical_message(method, target, body, timestamp, nonce)


def sign_helper(secret: bytes, message: bytes) -> str:
    return _b64_mac(derive_helper_verifier(secret), message)
