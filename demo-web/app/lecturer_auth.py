"""Lecturer sign-in with one cryptographic key.

The server keeps only an HMAC-SHA256 digest of the key. A correct key is
exchanged for a random lecturer session token that lives in memory.
The key itself is never logged and never sent back.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

SESSION_SECONDS = 12 * 3600
LOGIN_LIMIT = 10
LOGIN_WINDOW_SECONDS = 300


class LecturerAuthError(Exception):
    def __init__(self, reason: str, status: int = 401):
        super().__init__(reason)
        self.reason = reason
        self.status = status


def _digest(master: bytes, key: str) -> bytes:
    return hmac.new(master, b"zoomoodle-lecturer-key|" + key.strip().encode("utf-8"), hashlib.sha256).digest()


class LecturerAuth:
    def __init__(self, master: bytes, key: str, clock=None):
        if not key or len(key.strip()) < 16:
            raise ValueError("lecturer key is too short")
        self._master = master
        self._digest = _digest(master, key)
        self._clock = clock or time.time
        self._sessions: dict[str, float] = {}
        self._failures: list[float] = []

    def now(self) -> float:
        return float(self._clock())

    def sign_in(self, presented: str) -> str:
        now = self.now()
        self._failures = [stamp for stamp in self._failures if now - stamp < LOGIN_WINDOW_SECONDS]
        if len(self._failures) >= LOGIN_LIMIT:
            raise LecturerAuthError("login_limited", 429)
        candidate = _digest(self._master, str(presented or ""))
        if not hmac.compare_digest(candidate, self._digest):
            self._failures.append(now)
            raise LecturerAuthError("bad_lecturer_key", 401)
        token = secrets.token_urlsafe(32)
        self._sessions[hashlib.sha256(token.encode()).hexdigest()] = now + SESSION_SECONDS
        return token

    def check(self, token: str) -> bool:
        if not token:
            return False
        handle = hashlib.sha256(token.encode()).hexdigest()
        expires = self._sessions.get(handle)
        if expires is None:
            return False
        if self.now() > expires:
            self._sessions.pop(handle, None)
            return False
        return True

    def sign_out(self, token: str) -> None:
        if token:
            self._sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)
