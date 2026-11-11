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

from app.network_range import NetworkConfigError, address_in_network, hotspot_notes, validate_hotspot
from app.screen_qr import ScreenQrError, ScreenQrService
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
        self.bind_host = ""
        self.bind_port = 8787
        self.network_name = ""
        self.client_cidr = ""
        self._client_network = None
        self.challenges: dict[str, Challenge] = {}
        self.in_class: dict[str, bool] = {}
        self.remote: dict[str, bool] = {}
        self._helper_nonces: dict[str, float] = {}
        self.closed = False
        self.qr_required = True
        self.qr_accepted: dict[str, bool] = {}
        self._qr_used: dict[str, set[str]] = {}
        self.screen_qr = ScreenQrService(clock=self.now)

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

    def set_network(self, network_name: str, bind_host: str, client_cidr: str, bind_port: int = 8787) -> dict:
        try:
            port = int(bind_port)
        except (TypeError, ValueError) as exc:
            raise PresenceError("bad_network") from exc
        if port < 1 or port > 65535:
            raise PresenceError("bad_network")
        try:
            network, bind = validate_hotspot(bind_host, client_cidr)
        except NetworkConfigError as exc:
            raise PresenceError(exc.reason) from exc
        host = str(bind)
        self.bind_host = host
        self.bind_port = port
        self.client_cidr = str(network)
        self._client_network = network
        self.network_name = (network_name or "").strip()[:64]
        if bind.version == 6:
            self.bind_url = f"http://[{host}]:{port}"
        else:
            self.bind_url = f"http://{host}:{port}"
        return self.public_status()

    def socket_allowed(self, local: str, peer: str) -> None:
        if self._client_network is None or not self.bind_host:
            raise PresenceError("missing_network")
        if str(local or "").strip() != self.bind_host:
            mapped = local or ""
            if mapped.lower().startswith("::ffff:"):
                mapped = mapped.split(":")[-1]
            if mapped != self.bind_host:
                raise PresenceError("wrong_interface")
        if not address_in_network(peer or "", self._client_network):
            raise PresenceError("peer_out_of_range")

    def public_status(self) -> dict:
        notes = hotspot_notes(self._client_network) if self._client_network is not None else [
            "Enter the verifier address and the phone address range. Until then, no in-class checkmark is possible.",
        ]
        return {
            "helper_paired": bool(self.helper_id and self.helper_verifier),
            "bind_url": self.bind_url,
            "bind_host": self.bind_host,
            "bind_port": self.bind_port,
            "network_name": self.network_name,
            "client_cidr": self.client_cidr,
            "diagnostics": notes,
            "qr_required": self.qr_required,
            **self.screen_qr.public_params(),
        }

    def issue(self, room_id: str, entry_id: str, session_id: str) -> Challenge:
        if self.closed:
            raise PresenceError("presence_closed")
        if not self.helper_verifier or not self.bind_url or self._client_network is None:
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
        self.socket_allowed(str(body.get("local") or ""), str(body.get("peer") or ""))
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
        if self.qr_required and not self.qr_accepted.get(entry_id):
            raise PresenceError("qr_required")
        challenge.used = True
        self.in_class[entry_id] = True
        return challenge


    def set_qr_required(self, required: bool) -> dict:
        self.qr_required = bool(required)
        return self.public_status()

    def accept_screen_qr(self, room_id: str, entry_id: str, session_id: str, codes, room_key: bytes) -> list:
        if self.closed:
            raise PresenceError("presence_closed")
        if not entry_id or not session_id:
            raise PresenceError("presence_mismatch")
        try:
            frames = self.screen_qr.verify_sequence(room_key, room_id, codes, self.now())
        except ScreenQrError as exc:
            raise PresenceError(exc.reason) from exc
        used = self._qr_used.setdefault(entry_id, set())
        for frame in frames:
            if frame.token_id in used:
                raise PresenceError("qr_replay")
        used.update(frame.token_id for frame in frames)
        self.qr_accepted[entry_id] = True
        return frames


    def mark_remote(self, entry_id: str) -> None:
        if entry_id:
            self.remote[entry_id] = True

    def close(self) -> None:
        self.closed = True
        self.challenges.clear()
        self.qr_accepted.clear()
        self._qr_used.clear()
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
