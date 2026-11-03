"""In-memory lesson records. Names stay here and do not go to the agent."""

from __future__ import annotations

from dataclasses import dataclass, field

SEAT_ZONES = (
    "front-left",
    "front-right",
    "middle-left",
    "middle-right",
    "back-left",
    "back-right",
)


class SeatZone:
    def __init__(self, value: str):
        if value not in SEAT_ZONES:
            raise ValueError("unknown seat zone")
        self.value = value


@dataclass
class Challenge:
    id: str
    student_id: str
    device_id: str
    public_jwk: dict
    nonce: str
    issued_at: float
    used: bool = False


@dataclass
class AttendanceRecord:
    student_id: str
    student_name: str
    device_id: str
    mode: str
    seat_zone: str
    at: float
    confidence: str
    flags: list
    subnet: str
    token_late: bool
    external_token: str | None = None
    attendance_id: str = ""


@dataclass
class Poll:
    id: str
    question: str
    options: list[str]
    correct_option: str | None = None
    answers: list = field(default_factory=list)


@dataclass
class Comment:
    id: str
    student_id: str
    text: str
    at: float


@dataclass
class HomeworkSubmission:
    id: str
    student_id: str
    text: str
    at: float
