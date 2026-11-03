"""Per-student lesson session keys.

Check-in still uses the device ECDSA key and the room's rotating HMAC token.
After that proof, the server issues a separate session secret. The phone sees
the secret once. The server keeps only an HKDF-SHA256 verifier and uses it as
the HMAC key for later requests. The room key from ``crypto_tokens`` is not
reused here: its info string is ``zoomoodle-room-v1``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass, field

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SESSION_HKDF_SALT = b"zoomoodle-session-v1"
SESSION_HKDF_INFO = b"zoomoodle-session-mac"
SESSION_WINDOW_SECONDS = 60


class SessionError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def derive_session_verifier(session_secret: bytes) -> bytes:
    """MAC key stored on the server. Not the secret returned to the phone."""
    if len(session_secret) < 32:
        raise ValueError("session secret must be 32 bytes")
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SESSION_HKDF_SALT,
        info=SESSION_HKDF_INFO,
    ).derive(session_secret)


def canonical_message(method: str, target: str, body: bytes, timestamp: str, nonce: str) -> bytes:
    text = body.decode("utf-8")
    return f"{method.upper()}\n{target}\n{text}\n{timestamp}\n{nonce}".encode("utf-8")


def sign_message(verifier: bytes, message: bytes) -> str:
    mac = hmac.new(verifier, message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode("ascii").rstrip("=")


def _b64u_decode(text: str) -> bytes:
    raw = "".join(text.split())
    pad = "=" * ((4 - len(raw) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(raw + pad)
    except Exception as exc:
        raise SessionError("bad_session") from exc


def encode_secret(secret: bytes) -> str:
    return base64.urlsafe_b64encode(secret).decode("ascii").rstrip("=")


def decode_secret(token: str) -> bytes:
    raw = _b64u_decode(token)
    if len(raw) != 32:
        raise SessionError("bad_session")
    return raw


@dataclass
class StudentSession:
    id: str
    student_id: str
    verifier: bytes
    issued_at: float
    revoked: bool = False
    nonces: dict = field(default_factory=dict)


class SessionBook:
    def __init__(self, window_seconds: int = SESSION_WINDOW_SECONDS, clock=None):
        self.window_seconds = window_seconds
        self._clock = clock or time.time
        self.sessions: dict[str, StudentSession] = {}

    def now(self) -> float:
        return float(self._clock())

    def issue(self, student_id: str) -> tuple[str, str]:
        """Return ``(session_id, secret)``. The secret is not stored."""
        student_id = student_id.strip()
        if not student_id:
            raise SessionError("missing_identity")
        secret = os.urandom(32)
        verifier = derive_session_verifier(secret)
        session_id = secrets.token_hex(8)
        while session_id in self.sessions:
            session_id = secrets.token_hex(8)
        self.sessions[session_id] = StudentSession(
            id=session_id,
            student_id=student_id,
            verifier=verifier,
            issued_at=self.now(),
        )
        token = encode_secret(secret)
        del secret
        return session_id, token

    def revoke_all(self) -> None:
        for session in self.sessions.values():
            session.revoked = True

    def is_verified(self, student_id: str) -> bool:
        student_id = (student_id or "").strip()
        if not student_id:
            return False
        return any(
            session.student_id == student_id and not session.revoked
            for session in self.sessions.values()
        )

    def verify(
        self,
        *,
        session_id: str,
        timestamp: str,
        nonce: str,
        signature: str,
        message: bytes,
        write: bool,
        now: float | None = None,
    ) -> StudentSession:
        now = self.now() if now is None else float(now)
        session = self.sessions.get((session_id or "").strip())
        if session is None:
            raise SessionError("session_required")
        if write and session.revoked:
            raise SessionError("session_revoked")
        try:
            stamp = int(str(timestamp).strip())
        except (TypeError, ValueError):
            raise SessionError("session_expired") from None
        if abs(now - stamp) > self.window_seconds:
            raise SessionError("session_expired")
        nonce = (nonce or "").strip()
        if len(nonce) < 8 or len(nonce) > 128:
            raise SessionError("bad_session")
        if nonce in session.nonces:
            raise SessionError("session_replay")
        try:
            presented = _b64u_decode(signature or "")
        except SessionError:
            raise
        if not session.verifier or len(presented) != 32:
            raise SessionError("bad_session")
        expected = hmac.new(session.verifier, message, hashlib.sha256).digest()
        if not hmac.compare_digest(presented, expected):
            raise SessionError("bad_session")
        session.nonces[nonce] = stamp
        self._prune(session, now)
        return session

    def _prune(self, session: StudentSession, now: float) -> None:
        stale = [
            item
            for item, stamp in session.nonces.items()
            if abs(now - stamp) > self.window_seconds
        ]
        for item in stale:
            if item in session.nonces and abs(now - session.nonces[item]) > self.window_seconds:
                del session.nonces[item]
