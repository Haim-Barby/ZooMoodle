"""Student check-in and staged duplicate-name resolution.

Flow per student (one *claim* per phone session):
  remote:    pick name -> "remote". No network or barcode check.
  in class:  pick name -> university network (server-side IP) -> live
             flickering barcode for 2 s -> pick classroom area -> present.

Duplicate names, in stages:
  1. A verified in-class claim beats a remote claim on the same name; the
     remote claim is flagged for the lecturer.
  2. Two verified in-class claims on one name: both must re-pick their name.
  3. Still the same name after a re-pick: a one-time code goes to the roster
     email of that name; whoever types it gets the name.
  4. Still unresolved (wrong codes, expiry, the other device): the lecturer
     decides from the dashboard.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass, field

from app.domain import SEAT_ZONES
from app.screen_qr import ScreenQrError, ScreenQrService

REMOTE = "remote"
PENDING = "pending_barcode"
AREA = "needs_area"
PRESENT = "present"
FLAGGED = "flagged_remote"
REPICK = "repick"
EMAIL = "email_code"
LECTURER = "lecturer_decision"
REJECTED = "rejected"

CONFLICT_STATES = (FLAGGED, REPICK, EMAIL, LECTURER)
ACTIVE_STATES = (REMOTE, PRESENT)

CODE_SECONDS = 300
CODE_ATTEMPTS_PER_CLAIM = 3
CODE_ATTEMPTS_TOTAL = 6


class CheckinError(Exception):
    def __init__(self, reason: str, status: int = 409):
        super().__init__(reason)
        self.reason = reason
        self.status = status


@dataclass
class Claim:
    id: str
    entry_id: str
    mode: str
    state: str
    at: float
    zone: str = ""
    verified: bool = False
    repicked: int = 0
    owner: bool = False
    note: str = ""


@dataclass
class EmailChallenge:
    id: str
    entry_id: str
    salt: bytes
    code_mac: bytes
    expires_at: float
    claim_ids: list = field(default_factory=list)
    attempts: dict = field(default_factory=dict)
    used: bool = False
    closed: bool = False
    sent: bool = False
    demo_code: str = field(default="", repr=False)
    error: str = ""


def _code_mac(master: bytes, salt: bytes, code: str) -> bytes:
    return hmac.new(master, b"zoomoodle-email-code|" + salt + b"|" + code.encode(), hashlib.sha256).digest()


class CheckinBook:
    def __init__(self, master: bytes, roster, screen_qr: ScreenQrService, mailer=None, course: str = "", clock=None):
        self.master = master
        self.roster = roster
        self.screen_qr = screen_qr
        self.mailer = mailer
        self.course = course
        self._clock = clock or time.time
        self.claims: dict[str, Claim] = {}
        self.challenges: dict[str, EmailChallenge] = {}
        self._qr_used: dict[str, set] = {}

    def now(self) -> float:
        return float(self._clock())

    # ----- joining -------------------------------------------------------
    def join(self, entry_id: str, mode: str, on_campus: bool) -> Claim:
        entry = self.roster.get(entry_id)
        if entry is None:
            raise CheckinError("unknown_name", 404)
        if mode not in ("remote", "in_class"):
            raise CheckinError("bad_mode", 400)
        if mode == "in_class" and not on_campus:
            raise CheckinError("not_on_campus_network", 403)
        claim = Claim(
            id="c_" + secrets.token_hex(6),
            entry_id=entry.id,
            mode=mode,
            state=REMOTE if mode == "remote" else PENDING,
            at=self.now(),
        )
        self.claims[claim.id] = claim
        if mode == "remote":
            self._resolve(entry.id)
        return claim

    def get(self, claim_id: str) -> Claim:
        claim = self.claims.get(claim_id or "")
        if claim is None:
            raise CheckinError("unknown_claim", 404)
        return claim

    def submit_barcode(self, claim: Claim, codes, on_campus: bool, room_key: bytes, room_id: str) -> Claim:
        if claim.mode != "in_class" or claim.state != PENDING:
            raise CheckinError("not_waiting_for_barcode")
        if not on_campus:
            raise CheckinError("not_on_campus_network", 403)
        try:
            frames = self.screen_qr.verify_sequence(room_key, room_id, codes, self.now())
        except ScreenQrError as exc:
            raise CheckinError(exc.reason, 401 if exc.reason == "qr_mismatch" else 409) from exc
        used = self._qr_used.setdefault(claim.entry_id, set())
        if any(frame.token_id in used for frame in frames):
            raise CheckinError("qr_replay")
        used.update(frame.token_id for frame in frames)
        claim.verified = True
        claim.state = AREA
        self._resolve(claim.entry_id)
        return claim

    def choose_area(self, claim: Claim, zone: str) -> Claim:
        if zone not in SEAT_ZONES:
            raise CheckinError("bad_zone", 400)
        if claim.verified and claim.state in (REPICK, EMAIL, LECTURER):
            claim.zone = zone  # remembered; the name question is still open
            return claim
        if claim.state not in (AREA, PRESENT):
            raise CheckinError("area_not_allowed")
        claim.zone = zone
        claim.state = PRESENT
        return claim

    # ----- duplicate names -----------------------------------------------
    def repick(self, claim: Claim, entry_id: str) -> Claim:
        if claim.state != REPICK:
            raise CheckinError("repick_not_requested")
        entry = self.roster.get(entry_id)
        if entry is None:
            raise CheckinError("unknown_name", 404)
        claim.entry_id = entry.id
        claim.repicked += 1
        claim.state = PRESENT if claim.zone else AREA
        self._resolve(entry.id)
        return claim

    def submit_code(self, claim: Claim, code: str) -> Claim:
        self.expire()
        if claim.state != EMAIL:
            raise CheckinError("code_not_requested")
        challenge = self._open_challenge(claim.entry_id)
        if challenge is None or claim.id not in challenge.claim_ids:
            raise CheckinError("code_expired")
        tries = challenge.attempts.get(claim.id, 0)
        if tries >= CODE_ATTEMPTS_PER_CLAIM or sum(challenge.attempts.values()) >= CODE_ATTEMPTS_TOTAL:
            raise CheckinError("code_attempts", 429)
        candidate = "".join(ch for ch in str(code or "") if ch.isdigit())
        ok = len(candidate) == 6 and hmac.compare_digest(
            _code_mac(self.master, challenge.salt, candidate), challenge.code_mac
        )
        if not ok:
            challenge.attempts[claim.id] = tries + 1
            if (
                challenge.attempts[claim.id] >= CODE_ATTEMPTS_PER_CLAIM
                and all(challenge.attempts.get(cid, 0) >= CODE_ATTEMPTS_PER_CLAIM for cid in challenge.claim_ids)
            ) or sum(challenge.attempts.values()) >= CODE_ATTEMPTS_TOTAL:
                self._escalate(challenge, "code_attempts")
            raise CheckinError("bad_code", 401)
        challenge.used = True
        challenge.closed = True
        challenge.demo_code = ""
        claim.owner = True
        claim.state = PRESENT if claim.zone else AREA
        for other_id in challenge.claim_ids:
            if other_id != claim.id and self.claims[other_id].state == EMAIL:
                other = self.claims[other_id]
                other.state = LECTURER
                other.note = "other_device_confirmed_code"
        return claim

    def decide(self, claim_id: str, action: str) -> Claim:
        claim = self.get(claim_id)
        if action not in ("accept", "reject"):
            raise CheckinError("bad_action", 400)
        if action == "reject":
            claim.state = REJECTED
            claim.note = "lecturer_rejected"
            return claim
        claim.owner = True
        claim.note = "lecturer_accepted"
        if claim.mode == "remote":
            claim.state = REMOTE
        elif claim.verified:
            claim.state = PRESENT if claim.zone else AREA
        else:
            raise CheckinError("not_verified")
        for other in self.claims.values():
            if other.id != claim.id and other.entry_id == claim.entry_id and other.state != REJECTED:
                other.state = REJECTED
                other.owner = False
                other.note = "lecturer_gave_name_to_other"
        for challenge in self.challenges.values():
            if challenge.entry_id == claim.entry_id:
                challenge.closed = True
                challenge.demo_code = ""
        return claim

    def expire(self) -> None:
        now = self.now()
        for challenge in self.challenges.values():
            if not challenge.closed and now > challenge.expires_at:
                self._escalate(challenge, "code_expired")

    # ----- internals -----------------------------------------------------
    def _resolve(self, entry_id: str) -> None:
        claims = [c for c in self.claims.values() if c.entry_id == entry_id and c.state != REJECTED]
        owners = [c for c in claims if c.owner]
        if owners:
            for c in claims:
                if c.owner:
                    continue
                if c.mode == "remote":
                    c.state, c.note = FLAGGED, "name_already_confirmed"
                elif c.verified and c.state in (AREA, PRESENT):
                    c.state = LECTURER if c.repicked else REPICK
            return
        in_class = [c for c in claims if c.verified]
        remote = [c for c in claims if c.mode == "remote"]
        if in_class:
            for c in remote:
                c.state, c.note = FLAGGED, "in_class_wins"
        elif len(remote) > 1:
            for c in remote:
                c.state, c.note = FLAGGED, "same_name_remote"
        contenders = [c for c in in_class if c.state in (AREA, PRESENT, EMAIL, LECTURER)]
        if len(contenders) < 2:
            return
        if any(c.state == LECTURER for c in contenders):
            for c in contenders:
                c.state = LECTURER
            return
        if any(c.repicked for c in contenders):
            self._start_email(entry_id, contenders)
        else:
            for c in contenders:
                c.state = REPICK

    def _open_challenge(self, entry_id: str) -> EmailChallenge | None:
        for challenge in self.challenges.values():
            if challenge.entry_id == entry_id and not challenge.closed:
                return challenge
        return None

    def _start_email(self, entry_id: str, contenders: list[Claim]) -> None:
        challenge = self._open_challenge(entry_id)
        if challenge is None:
            code = f"{secrets.randbelow(10 ** 6):06d}"
            salt = os.urandom(16)
            challenge = EmailChallenge(
                id="e_" + secrets.token_hex(6),
                entry_id=entry_id,
                salt=salt,
                code_mac=_code_mac(self.master, salt, code),
                expires_at=self.now() + CODE_SECONDS,
            )
            entry = self.roster.entries.get(entry_id)
            result = None
            if self.mailer is not None and entry is not None:
                result = self.mailer.send_code(self.roster.email_for(entry_id), entry.display, self.course, code)
            if result is not None and result.sent:
                challenge.sent = True
            else:
                challenge.demo_code = code
                challenge.error = result.error if result is not None else ""
            del code
            self.challenges[challenge.id] = challenge
        for c in contenders:
            c.state = EMAIL
            if c.id not in challenge.claim_ids:
                challenge.claim_ids.append(c.id)

    def _escalate(self, challenge: EmailChallenge, why: str) -> None:
        challenge.closed = True
        challenge.demo_code = ""
        for cid in challenge.claim_ids:
            claim = self.claims.get(cid)
            if claim is not None and claim.state == EMAIL:
                claim.state = LECTURER
                claim.note = why

    # ----- views -----------------------------------------------------------
    def counts(self) -> dict:
        states = [c.state for c in self.claims.values()]
        return {
            "in_class": states.count(PRESENT),
            "remote": states.count(REMOTE),
            "pending": sum(1 for s in states if s in (PENDING, AREA)),
            "conflicts": sum(1 for s in states if s in CONFLICT_STATES),
        }

    def zone_counts(self) -> dict:
        counts = {zone: 0 for zone in SEAT_ZONES}
        for claim in self.claims.values():
            if claim.state == PRESENT and claim.zone in counts:
                counts[claim.zone] += 1
        return counts

    def challenge_view(self, entry_id: str) -> dict | None:
        challenge = None
        for item in self.challenges.values():
            if item.entry_id == entry_id:
                challenge = item
        if challenge is None:
            return None
        view = {
            "open": not challenge.closed,
            "sent": challenge.sent,
            "expires_in": max(0, round(challenge.expires_at - self.now())),
        }
        if not challenge.closed and not challenge.sent:
            view["demo_label"] = "מצב הדגמה – המייל לא נשלח"
            view["demo_code"] = challenge.demo_code
        return view
