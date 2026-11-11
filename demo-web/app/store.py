"""In-memory rooms. Restarting the process clears them."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time

from app.checkin import CheckinBook
from app.config import Settings
from app.domain import SEAT_ZONES, Comment, HomeworkFile, Poll, Question
from app.llm.tools import pseudonym, redact
from app.mailer import Mailer
from app.roster import RoomRoster
from app.screen_qr import ScreenQrService
from app.session_keys import SessionBook



_OPTION_SPLIT = re.compile(r"[,;|/،]\s*|\r?\n+")
_OPTION_WORD_SPLIT = re.compile(r"\s+(?:או|or|vs\.?)\s+", re.IGNORECASE)


def parse_poll_options(options) -> list[str]:
    """Accept a list or a single string typed with commas, slashes, or 'או'."""
    if isinstance(options, str):
        parts = _split_option_text(options)
    else:
        parts = []
        for option in options or []:
            text = str(option).strip()
            if not text:
                continue
            pieces = _split_option_text(text)
            parts.extend(pieces if len(pieces) > 1 else [text])
    cleaned: list[str] = []
    for text in parts:
        text = text.strip()
        if text and text not in cleaned:
            cleaned.append(text[:80])
    return cleaned


def _split_option_text(text: str) -> list[str]:
    parts = [item.strip() for item in _OPTION_SPLIT.split(text) if item.strip()]
    if len(parts) >= 2:
        return parts
    parts = [item.strip() for item in _OPTION_WORD_SPLIT.split(text) if item.strip()]
    return parts if len(parts) >= 2 else ([text.strip()] if text.strip() else [])


def resolve_correct_option(correct, options: list[str]) -> str | None:
    if correct in (None, ""):
        return None
    text = str(correct).strip()
    if text in options:
        return text
    if text.isdigit():
        index = int(text)
        if 1 <= index <= len(options):
            return options[index - 1]
    raise StoreError("correct_option_must_be_one_of_the_options")


MAX_HOMEWORK_BYTES = 5 * 1024 * 1024


class StoreError(Exception):
    def __init__(self, reason: str, status: int = 400):
        super().__init__(reason)
        self.reason = reason
        self.status = status


def derive_room_key(master: bytes, salt: bytes) -> bytes:
    return hmac.new(master, b"zoomoodle-room-v2|" + salt, hashlib.sha256).digest()


class Room:
    def __init__(self, room_id: str, title: str, key: bytes, settings: Settings, mailer: Mailer):
        self.id = room_id
        self.title = title
        self.key = key
        self.created_at = time.time()
        self.closed = False
        self.roster = RoomRoster(settings.master_secret)
        self.screen_qr = ScreenQrService()
        self.checkin = CheckinBook(settings.master_secret, self.roster, self.screen_qr, mailer, settings.course_name)
        self.sessions = SessionBook()
        self.polls: list[Poll] = []
        self.comments: list[Comment] = []
        self.questions: list[Question] = []
        self.homework: list[HomeworkFile] = []
        self.transcript = ""
        self.summary = ""
        self.summary_source = ""


class Store:
    def __init__(self, settings: Settings, mailer: Mailer | None = None):
        self.settings = settings
        self.mailer = mailer or Mailer(settings)
        self.rooms: dict[str, Room] = {}

    def create_room(self, title: str) -> Room:
        default = f"{self.settings.course_name} – שבוע {self.settings.course_week}"
        title = (title or default).strip()[:120] or default
        room_id = secrets.token_hex(4)
        while room_id in self.rooms:
            room_id = secrets.token_hex(4)
        room = Room(room_id, title, derive_room_key(self.settings.master_secret, os.urandom(16)), self.settings, self.mailer)
        self.rooms[room_id] = room
        return room

    def get(self, room_id: str) -> Room:
        room = self.rooms.get(room_id)
        if room is None:
            raise StoreError("unknown_room", 404)
        return room

    def close_room(self, room_id: str) -> Room:
        room = self.get(room_id)
        room.closed = True
        return room

    # ----- polls, notes, questions ---------------------------------------
    def add_poll(self, room: Room, question: str, options: list, correct) -> Poll:
        question = (question or "").strip()
        cleaned = parse_poll_options(options)
        if not question or len(cleaned) < 2 or len(cleaned) > 6:
            raise StoreError("poll_needs_a_question_and_2_to_6_options")
        correct_option = resolve_correct_option(correct, cleaned)
        poll = Poll(id=secrets.token_hex(4), question=question[:200], options=cleaned, correct_option=correct_option)
        room.polls.append(poll)
        return poll

    def answer_poll(self, room: Room, poll_id: str, student_id: str, option: str, zone: str) -> Poll:
        poll = next((item for item in room.polls if item.id == poll_id), None)
        if poll is None:
            raise StoreError("unknown_poll", 404)
        if not poll.open:
            raise StoreError("poll_closed", 409)
        if option not in poll.options:
            raise StoreError("bad_option")
        if zone != "remote" and zone not in SEAT_ZONES:
            raise StoreError("bad_zone")
        if any(answer["student_id"] == student_id for answer in poll.answers):
            raise StoreError("already_answered", 409)
        poll.answers.append({"student_id": student_id, "option": option, "seat_zone": zone})
        return poll

    def add_comment(self, room: Room, student_id: str, text: str) -> Comment:
        text = (text or "").strip()
        if not text:
            raise StoreError("missing_comment")
        comment = Comment(id=secrets.token_hex(4), student_id=student_id, text=text[:2000], at=time.time())
        room.comments.append(comment)
        return comment

    def add_question(self, room: Room, student_id: str, text: str) -> Question:
        text = (text or "").strip()
        if not text:
            raise StoreError("missing_question")
        question = Question(id=secrets.token_hex(4), student_id=student_id, text=text[:1000], at=time.time())
        room.questions.append(question)
        return question

    def upvote_question(self, room: Room, question_id: str, student_id: str) -> Question:
        question = next((item for item in room.questions if item.id == question_id), None)
        if question is None:
            raise StoreError("unknown_question", 404)
        if student_id in question.upvotes:
            raise StoreError("already_upvoted", 409)
        question.upvotes.append(student_id)
        return question

    @staticmethod
    def questions_by_votes(room: Room) -> list[Question]:
        return sorted(room.questions, key=lambda item: (-len(item.upvotes), item.at, item.id))

    # ----- homework --------------------------------------------------------
    def add_homework(self, room: Room, title: str, filename: str, content_type: str, data: bytes) -> HomeworkFile:
        if not data:
            raise StoreError("missing_file")
        if len(data) > MAX_HOMEWORK_BYTES:
            raise StoreError("file_too_large", 413)
        safe_name = "".join(ch for ch in os.path.basename(filename or "homework") if ch not in '\\/:*?"<>|\r\n')[:120]
        item = HomeworkFile(
            id="hw_" + secrets.token_hex(4),
            title=(title or safe_name or "שיעורי בית").strip()[:120],
            filename=safe_name or "homework",
            content_type=(content_type or "application/octet-stream")[:100],
            data=data,
            at=time.time(),
        )
        room.homework.append(item)
        return item

    # ----- summary input -----------------------------------------------------
    def snapshot(self, room: Room) -> tuple[dict, list[str], list[str]]:
        names = []
        ids = list(room.checkin.claims)
        for claim in room.checkin.claims.values():
            entry = room.roster.entries.get(claim.entry_id)
            if entry and entry.display not in names:
                names.append(entry.display)

        def clean(text: str) -> str:
            return redact(text, names, ids)

        snapshot = {
            "room_id": room.id,
            "title": room.title,
            "transcript": clean(room.transcript),
            "polls": [
                {
                    "id": poll.id,
                    "question": poll.question,
                    "options": list(poll.options),
                    "correct_option": poll.correct_option,
                    "answers": [
                        {"option": a["option"], "seat_zone": a["seat_zone"], "pseudonym": pseudonym(a["student_id"])}
                        for a in poll.answers
                    ],
                }
                for poll in room.polls
            ],
            "comments": [
                {"id": c.id, "pseudonym": pseudonym(c.student_id), "text": clean(c.text)}
                for c in room.comments
            ]
            + [
                {"id": q.id, "pseudonym": pseudonym(q.student_id), "text": "שאלה: " + clean(q.text), "votes": len(q.upvotes)}
                for q in room.questions
            ],
            "homework": [],
            "attention": {"empty": True, "zones": {}, "source": "none", "disclaimer": "No camera data in this demo.", "samples": []},
        }
        return snapshot, names, ids
