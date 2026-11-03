"""Device binding keys. Browsers send a P-256 public JWK and a raw ECDSA signature."""

from __future__ import annotations

import base64
import hashlib
import hmac

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature


def _b64u(text: str) -> bytes:
    pad = "=" * ((4 - len(text) % 4) % 4)
    return base64.urlsafe_b64decode(text + pad)


def device_id_from_public_jwk(jwk: dict) -> str:
    material = f"{jwk.get('x', '')}.{jwk.get('y', '')}".encode("ascii")
    return hashlib.sha256(material).hexdigest()[:16]


def public_key_from_jwk(jwk: dict):
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise ValueError("unsupported device key")
    x_bytes = _b64u(jwk["x"])
    y_bytes = _b64u(jwk["y"])
    if len(x_bytes) != 32 or len(y_bytes) != 32:
        raise ValueError("unsupported device key")
    x = int.from_bytes(x_bytes, "big")
    y = int.from_bytes(y_bytes, "big")
    return ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()


def verify_signature(jwk: dict, message: bytes, signature: bytes) -> bool:
    if len(signature) != 64:
        return False
    try:
        key = public_key_from_jwk(jwk)
        r = int.from_bytes(signature[:32], "big")
        s = int.from_bytes(signature[32:], "big")
        key.verify(encode_dss_signature(r, s), message, ec.ECDSA(hashes.SHA256()))
        return True
    except Exception:
        return False


def signature_message(challenge_id: str, nonce: str) -> bytes:
    return f"{challenge_id}|{nonce}".encode("utf-8")


def ids_match(presented: str, jwk: dict) -> bool:
    expected = device_id_from_public_jwk(jwk)
    if len(presented) != len(expected):
        return False
    return hmac.compare_digest(presented, expected)
