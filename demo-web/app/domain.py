"""In-memory lesson records."""

from __future__ import annotations

from dataclasses import dataclass, field

SEAT_ZONES = (
    "front-left",
    "front-center",
    "front-right",
    "middle-left",
    "middle-center",
    "middle-right",
    "back-left",
    "back-center",
    "back-right",
)


@dataclass
class Poll:
    id: str
    question: str
    options: list[str]
    correct_option: str | None = None
    answers: list = field(default_factory=list)
    open: bool = True


@dataclass
class Comment:
    id: str
    student_id: str
    text: str
    at: float


@dataclass
class Question:
    id: str
    student_id: str
    text: str
    at: float
    upvotes: list = field(default_factory=list)


@dataclass
class HomeworkFile:
    id: str
    title: str
    filename: str
    content_type: str
    data: bytes = field(repr=False)
    at: float = 0.0
