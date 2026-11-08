"""Local presence verifier.

The phone opens this process with a top-level navigation. The helper accepts
the request only on the configured interface, tells the classroom server it
saw the challenge, and sends the phone back to the HTTPS app. It does not
trust a return URL from the query string, and it does not log the helper key.
"""

from __future__ import annotations

import json
import secrets
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.presence import derive_helper_verifier, sign_helper
from app.session_keys import canonical_message, decode_secret

REFUSED_BINDS = {"", "0.0.0.0", "::", "::0"}


def connection_matches_bind(sockname: tuple, bind_host: str) -> bool:
    host = str(sockname[0] if sockname else "")
    if host.startswith("::ffff:"):
        host = host.rsplit(":", 1)[-1]
    return bool(bind_host) and host == bind_host


def student_return(public_origin: str, room_id: str, challenge_id: str) -> str:
    origin = (public_origin or "").rstrip("/")
    if not origin.startswith("https://") and not origin.startswith("http://"):
        raise ValueError("public origin must be http or https")
    if "@" in origin.split("://", 1)[-1]:
        raise ValueError("public origin must not include credentials")
    return f"{origin}/student?room={room_id}#presence={challenge_id}"


class PresenceHelper:
    def __init__(self, bind_host: str, server: str, room_id: str, helper_id: str, helper_key: str, public_origin: str):
        if bind_host in REFUSED_BINDS:
            raise ValueError("bind must be one interface address, not every interface")
        self.bind_host = bind_host
        self.server = server.rstrip("/")
        self.room_id = room_id
        self.helper_id = helper_id
        self.helper_key = helper_key
        self.public_origin = public_origin
        # Derive once so a mistaken log of this object is less likely to include the secret.
        self._verifier = derive_helper_verifier(decode_secret(helper_key))
        self.observations = 0

    def prove(self, challenge_id: str, sockname: tuple) -> tuple[int, str]:
        if not connection_matches_bind(sockname, self.bind_host):
            return 403, ""
        if not challenge_id or len(challenge_id) > 80:
            return 400, ""
        self._observe(challenge_id)
        self.observations += 1
        return 302, student_return(self.public_origin, self.room_id, challenge_id)

    def _observe(self, challenge_id: str) -> None:
        path = f"/api/rooms/{self.room_id}/presence/observe"
        body = json.dumps({"challenge_id": challenge_id}, separators=(",", ":")).encode("utf-8")
        stamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        message = canonical_message("POST", path, body, stamp, nonce)
        signature = sign_helper(decode_secret(self.helper_key), message)
        request = urllib.request.Request(
            self.server + path,
            data=body,
            method="POST",
            headers={
                "content-type": "application/json",
                "x-zoomoodle-session": self.helper_id,
                "x-zoomoodle-timestamp": stamp,
                "x-zoomoodle-nonce": nonce,
                "x-zoomoodle-signature": signature,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError("observe rejected") from RuntimeError(detail[:120])


class _Handler(BaseHTTPRequestHandler):
    helper: PresenceHelper

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/prove":
            self.send_error(404)
            return
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        challenge_id = ""
        for part in query.split("&"):
            if part.startswith("c="):
                challenge_id = part[2:]
        try:
            status, location = self.helper.prove(challenge_id, self.connection.getsockname())
        except Exception:
            self.send_error(502)
            return
        if status == 302:
            self.send_response(302)
            self.send_header("location", location)
            self.send_header("cache-control", "no-store")
            self.end_headers()
            return
        self.send_error(status)

    def log_message(self, fmt, *args):
        # Query strings can carry a challenge id. Do not write them.
        return


def serve(helper: PresenceHelper, port: int) -> ThreadingHTTPServer:
    _Handler.helper = helper
    server = ThreadingHTTPServer((helper.bind_host, port), _Handler)
    return server
