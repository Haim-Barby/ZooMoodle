import base64
import json
import secrets
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from app.config import Settings
from app.device_keys import device_id_from_public_jwk, signature_message
from app.session_keys import canonical_message, decode_secret, derive_session_verifier, sign_message


def make_settings(**overrides) -> Settings:
    values = dict(
        master_secret=b"test-master-secret-which-is-long",
        lecturer_token="lecturer-test-token",
        ephemeral_master_secret=False,
        generated_lecturer_token=False,
        token_window_seconds=5,
        grace_windows=1,
        challenge_max_age_seconds=8.0,
        allowed_subnets=(),
        llm_provider="",
        llm_model="",
        llm_base_url="",
        llm_api_key="",
        llm_timeout_seconds=8.0,
        agent_max_steps=8,
    )
    values.update(overrides)
    return Settings(**values)


def make_device():
    private = ec.generate_private_key(ec.SECP256R1())
    numbers = private.public_key().public_numbers()

    def b64u(number: int) -> str:
        return base64.urlsafe_b64encode(number.to_bytes(32, "big")).decode("ascii").rstrip("=")

    jwk = {"kty": "EC", "crv": "P-256", "x": b64u(numbers.x), "y": b64u(numbers.y)}
    device_id = device_id_from_public_jwk(jwk)

    def sign(challenge_id: str, nonce: str) -> bytes:
        der = private.sign(signature_message(challenge_id, nonce), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        return r.to_bytes(32, "big") + s.to_bytes(32, "big")

    return {"jwk": jwk, "device_id": device_id, "sign": sign}


def signed_request(client, creds, method, path, payload=None, timestamp=None, nonce=None):
    """Sign a lesson action with the HKDF verifier, not the raw phone secret."""
    body = b"" if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    stamp = str(int(time.time()) if timestamp is None else timestamp)
    nonce = nonce or secrets.token_hex(16)
    message = canonical_message(method, path, body, stamp, nonce)
    verifier = derive_session_verifier(decode_secret(creds["session_key"]))
    headers = {
        "content-type": "application/json",
        "x-zoomoodle-session": creds["session_id"],
        "x-zoomoodle-timestamp": stamp,
        "x-zoomoodle-nonce": nonce,
        "x-zoomoodle-signature": sign_message(verifier, message),
    }
    return client.request(method, path, content=body, headers=headers)
