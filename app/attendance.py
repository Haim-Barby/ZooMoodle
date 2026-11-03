"""Check-in, device binding, and anomaly flags."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from app.crypto_tokens import TokenService
from app.device_keys import ids_match, signature_message, verify_signature
from app.domain import SEAT_ZONES, AttendanceRecord, Challenge, SeatZone


class CheckInError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def score_confidence(mode: str, late: bool, subnet: str, flags: list[str]) -> str:
    serious = {"shared_device", "multi_device", "both_modes"}
    if serious.intersection(flags):
        return "low"
    weaknesses = 0
    if late:
        weaknesses += 1
    if subnet == "mismatch":
        weaknesses += 1
    if mode == "remote":
        weaknesses += 1
    if weaknesses >= 2:
        return "low"
    if weaknesses == 1:
        return "medium"
    return "high"


class DeviceBinding:
    """First public key seen for a device id is the one we keep."""

    def __init__(self):
        self.public_keys: dict[str, dict] = {}
        self.owner: dict[str, str] = {}

    def observe(self, device_id: str, student_id: str, public_jwk: dict) -> None:
        self.public_keys.setdefault(device_id, public_jwk)
        self.owner.setdefault(device_id, student_id)


class AnomalyDetector:
    def apply(self, records: list[AttendanceRecord]) -> None:
        modes: dict[str, set[str]] = {}
        devices: dict[str, set[str]] = {}
        students: dict[str, set[str]] = {}
        for record in records:
            modes.setdefault(record.student_id, set()).add(record.mode)
            devices.setdefault(record.student_id, set()).add(record.device_id)
            students.setdefault(record.device_id, set()).add(record.student_id)
        for record in records:
            flags: list[str] = []
            if record.token_late:
                flags.append("late_token")
            if record.subnet == "mismatch":
                flags.append("subnet_mismatch")
            if modes.get(record.student_id, set()) >= {"in_class", "remote"}:
                flags.append("both_modes")
            if len(devices.get(record.student_id, ())) > 1:
                flags.append("multi_device")
            if len(students.get(record.device_id, ())) > 1:
                flags.append("shared_device")
            record.flags = flags
            record.confidence = score_confidence(record.mode, record.token_late, record.subnet, flags)


@dataclass
class CheckInOutcome:
    record: AttendanceRecord


class AttendanceService:
    def __init__(self, tokens: TokenService, max_challenge_age: float = 8.0):
        self.tokens = tokens
        self.max_challenge_age = max_challenge_age
        self.binding = DeviceBinding()
        self.detector = AnomalyDetector()
        self.challenges: dict[str, Challenge] = {}
        self.records: list[AttendanceRecord] = []
        self.redeemed: set[tuple[str, str]] = set()

    def open_challenge(self, student_id: str, device_id: str, public_jwk: dict, now: float) -> Challenge:
        student_id = student_id.strip()
        device_id = device_id.strip()
        if not student_id or not device_id:
            raise CheckInError("missing_identity")
        if not isinstance(public_jwk, dict) or not ids_match(device_id, public_jwk):
            raise CheckInError("device_mismatch")
        challenge = Challenge(
            id=secrets.token_hex(8),
            student_id=student_id,
            device_id=device_id,
            public_jwk=public_jwk,
            nonce=secrets.token_hex(8),
            issued_at=now,
        )
        self.challenges[challenge.id] = challenge
        return challenge

    def check_in(
        self,
        *,
        challenge_id: str,
        signature: bytes,
        mode: str,
        token_code: str | None,
        seat_zone: str,
        subnet: str,
        room_key: bytes,
        room_id: str,
        student_name: str,
        now: float,
    ) -> CheckInOutcome:
        challenge = self.challenges.get(challenge_id)
        if challenge is None or challenge.used:
            raise CheckInError("challenge_used")
        if now - challenge.issued_at > self.max_challenge_age:
            raise CheckInError("challenge_expired")
        if mode not in ("in_class", "remote"):
            raise CheckInError("bad_mode")
        try:
            zone = SeatZone(seat_zone).value
        except ValueError:
            raise CheckInError("bad_zone") from None
        message = signature_message(challenge.id, challenge.nonce)
        if not verify_signature(challenge.public_jwk, message, signature):
            raise CheckInError("bad_signature")

        late = False
        external = None
        if mode == "in_class":
            if not token_code:
                raise CheckInError("missing_code")
            verdict = self.tokens.verify(room_key, room_id, token_code, now)
            if not verdict.ok:
                raise CheckInError("bad_token")
            code = "".join(token_code.split()).upper()
            slot = (code, challenge.device_id)
            if slot in self.redeemed:
                raise CheckInError("reused_token")
            self.redeemed.add(slot)
            late = verdict.late
        else:
            external = secrets.token_hex(8)

        challenge.used = True
        self.binding.observe(challenge.device_id, challenge.student_id, challenge.public_jwk)
        record = AttendanceRecord(
            student_id=challenge.student_id,
            student_name=student_name.strip()[:80],
            device_id=challenge.device_id,
            mode=mode,
            seat_zone=zone,
            at=now,
            confidence="high",
            flags=[],
            subnet=subnet,
            token_late=late,
            external_token=external,
        )
        self.records.append(record)
        self.detector.apply(self.records)
        return CheckInOutcome(record=record)
