"""Student check-in and staged duplicate-name resolution.

Flow per student (one *claim* per phone session):
  remote:    pick name -> "remote". No network or barcode check.
  in class:  pick name -> university network (server-side IP) -> live
             flickering barcode for 2 s -> pick classroom area -> present.

Duplicate names, in stages:
  1. A verified in-class claim beats a remote claim on the same name; the
     remote claim is flagged for the lecturer.
  2. Two verified in-class claims on one name: both must re-pick their name.
  3. Still the same name after a re-pick: the lecturer decides from the
     dashboard (and can ask in class).
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from app.domain import SEAT_ZONES
from app.screen_qr import ScreenQrError, ScreenQrService

REMOTE = "remote"
PENDING = "pending_barcode"
AREA = "needs_area"
PRESENT = "present"
FLAGGED = "flagged_remote"
REPICK = "repick"
LECTURER = "lecturer_decision"
REJECTED = "rejected"

CONFLICT_STATES = (FLAGGED, REPICK, LECTURER)
ACTIVE_STATES = (REMOTE, PRESENT)


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


class CheckinBook:
    def __init__(self, roster, screen_qr: ScreenQrService, clock=None):
        self.roster = roster
        self.screen_qr = screen_qr
        self._clock = clock or time.time
        self.claims: dict[str, Claim] = {}
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
        if claim.verified and claim.state in (REPICK, LECTURER):
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
        return claim

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
        contenders = [c for c in in_class if c.state in (AREA, PRESENT, LECTURER)]
        if len(contenders) < 2:
            return
        # Stage 2 (first collision): both re-pick. Stage 3 (again): the lecturer.
        final = any(c.state == LECTURER or c.repicked for c in contenders)
        for c in contenders:
            c.state = LECTURER if final else REPICK

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
