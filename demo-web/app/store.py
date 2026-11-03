"""In-memory rooms. Restarting the process clears them."""

from __future__ import annotations

import os
import secrets
import time

from app.attention import AttentionAggregator
from app.config import Settings
from app.crypto_tokens import IssuedToken, KeyManager, TokenService
from app.attendance import AttendanceService
from app.domain import SEAT_ZONES, Comment, HomeworkSubmission, Poll, Question
from app.llm.providers import LLMConfig
from app.llm.tools import pseudonym, redact
from app.session_keys import SessionBook


class StoreError(Exception):
    def __init__(self, reason: str, status: int = 400):
        super().__init__(reason)
        self.reason = reason
        self.status = status


class Room:
    def __init__(self, room_id: str, title: str, salt: bytes, key: bytes, attendance: AttendanceService):
        self.id = room_id
        self.title = title
        self.salt = salt
        self.key = key
        self.created_at = time.time()
        self.broadcast: IssuedToken | None = None
        self.attendance = attendance
        self.polls: list[Poll] = []
        self.comments: list[Comment] = []
        self.questions: list[Question] = []
        self.homework: list[HomeworkSubmission] = []
        self.transcript = ""
        self.attention = AttentionAggregator()
        self.names: dict[str, str] = {}
        self.closed = False
        self.audio_band = "ultrasonic"
        self.proof = "both"
        self.summary_draft = ""
        self.summary_published = ""
        self.sessions = SessionBook()


class Store:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.keys = KeyManager(settings.master_secret)
        self.tokens = TokenService(
            window_seconds=settings.token_window_seconds,
            grace_windows=settings.grace_windows,
        )
        self.rooms: dict[str, Room] = {}
        self.llm = LLMConfig(
            provider=settings.llm_provider,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    def create_room(self, title: str) -> Room:
        title = (title or "Untitled lesson").strip()[:120] or "Untitled lesson"
        salt = os.urandom(16)
        room_id = secrets.token_hex(3)
        while room_id in self.rooms:
            room_id = secrets.token_hex(3)
        room = Room(
            room_id,
            title,
            salt,
            self.keys.derive_room_key(salt),
            AttendanceService(self.tokens, self.settings.challenge_max_age_seconds),
        )
        self.rooms[room_id] = room
        return room

    def close_room(self, room_id: str) -> Room:
        room = self.get(room_id)
        room.closed = True
        room.sessions.revoke_all()
        return room

    def get(self, room_id: str) -> Room:
        room = self.rooms.get(room_id)
        if room is None:
            raise StoreError("unknown_room", 404)
        return room

    def current_token(self, room_id: str) -> IssuedToken:
        room = self.get(room_id)
        now = self.tokens.now()
        window = self.tokens.window_for(now)
        if room.broadcast is None or room.broadcast.window != window:
            room.broadcast = self.tokens.issue(room.key, room.id, now)
        return room.broadcast

    def remember_name(self, room: Room, student_id: str, student_name: str) -> None:
        if student_name:
            room.names[student_id] = student_name.strip()[:80]

    def add_poll(self, room_id: str, question: str, options: list[str], correct: str | None) -> Poll:
        room = self.get(room_id)
        question = (question or "").strip()
        cleaned = []
        for option in options or []:
            text = str(option).strip()
            if text and text not in cleaned:
                cleaned.append(text[:80])
        if not question or len(cleaned) < 2 or len(cleaned) > 6:
            raise StoreError("poll_needs_a_question_and_2_to_6_options")
        if correct is not None and correct not in cleaned:
            raise StoreError("correct_option_must_be_one_of_the_options")
        poll = Poll(id=secrets.token_hex(4), question=question[:200], options=cleaned, correct_option=correct)
        room.polls.append(poll)
        return poll

    def answer_poll(self, room_id: str, poll_id: str, student_id: str, option: str, seat_zone: str) -> Poll:
        room = self.get(room_id)
        student_id = student_id.strip()
        if not student_id:
            raise StoreError("missing_identity")
        zone = (seat_zone or "").strip()
        # Remote students have no seat. An empty zone is still rejected.
        if zone != "remote" and zone not in SEAT_ZONES:
            raise StoreError("bad_zone")
        poll = next((item for item in room.polls if item.id == poll_id), None)
        if poll is None:
            raise StoreError("unknown_poll", 404)
        if option not in poll.options:
            raise StoreError("bad_option")
        if any(answer["student_id"] == student_id for answer in poll.answers):
            raise StoreError("already_answered")
        poll.answers.append({"student_id": student_id, "option": option, "seat_zone": zone})
        return poll

    def add_question(self, room_id: str, student_id: str, text: str) -> Question:
        room = self.get(room_id)
        student_id = student_id.strip()
        text = (text or "").strip()
        if not student_id:
            raise StoreError("missing_identity")
        if not text:
            raise StoreError("missing_question")
        question = Question(
            id=secrets.token_hex(4),
            student_id=student_id[:80],
            text=text[:1000],
            at=time.time(),
        )
        room.questions.append(question)
        return question

    def upvote_question(self, room_id: str, question_id: str, student_id: str) -> Question:
        room = self.get(room_id)
        student_id = student_id.strip()
        if not student_id:
            raise StoreError("missing_identity")
        question = next((item for item in room.questions if item.id == question_id), None)
        if question is None:
            raise StoreError("unknown_question", 404)
        if student_id in question.upvotes:
            raise StoreError("already_upvoted")
        question.upvotes.append(student_id[:80])
        return question

    def questions_by_votes(self, room_id: str) -> list[Question]:
        room = self.get(room_id)
        return sorted(room.questions, key=lambda item: (-len(item.upvotes), item.at, item.id))

    def save_summary_draft(self, room_id: str, text: str) -> str:
        room = self.get(room_id)
        room.summary_draft = (text or "").strip()[:20000]
        return room.summary_draft

    def publish_summary(self, room_id: str, text: str | None) -> str:
        room = self.get(room_id)
        if text is None:
            published = room.summary_draft.strip()
        else:
            published = str(text).strip()[:20000]
            room.summary_draft = published
        if not published:
            raise StoreError("missing_summary")
        room.summary_published = published
        return published

    def add_comment(self, room_id: str, student_id: str, student_name: str, text: str) -> Comment:
        room = self.get(room_id)
        student_id = student_id.strip()
        text = (text or "").strip()
        if not student_id or not text:
            raise StoreError("missing_comment")
        self.remember_name(room, student_id, student_name)
        comment = Comment(id=secrets.token_hex(4), student_id=student_id, text=text[:2000], at=time.time())
        room.comments.append(comment)
        return comment

    def add_homework(self, room_id: str, student_id: str, student_name: str, text: str) -> HomeworkSubmission:
        room = self.get(room_id)
        student_id = student_id.strip()
        text = (text or "").strip()
        if not student_id or not text:
            raise StoreError("missing_homework")
        self.remember_name(room, student_id, student_name)
        item = HomeworkSubmission(
            id="hw_" + secrets.token_hex(4),
            student_id=student_id,
            text=text[:20000],
            at=time.time(),
        )
        room.homework.append(item)
        return item

    def set_transcript(self, room_id: str, text: str) -> int:
        room = self.get(room_id)
        room.transcript = (text or "")[:200000]
        return len(room.transcript)

    def snapshot(self, room_id: str) -> tuple[dict, list[str], list[str]]:
        room = self.get(room_id)
        names = [name for name in room.names.values() if name]
        student_ids = list(room.names)
        # Also redact names that appear only on attendance records.
        for record in room.attendance.records:
            if record.student_name and record.student_name not in names:
                names.append(record.student_name)
            if record.student_id not in student_ids:
                student_ids.append(record.student_id)

        def clean(text: str) -> str:
            return redact(text, names, student_ids)

        attention = room.attention.by_zone()
        attention["samples"] = list(room.attention.samples)
        polls = []
        for poll in room.polls:
            polls.append(
                {
                    "id": poll.id,
                    "question": poll.question,
                    "options": list(poll.options),
                    "correct_option": poll.correct_option,
                    "answers": [
                        {
                            "option": answer["option"],
                            "seat_zone": answer["seat_zone"],
                            "pseudonym": pseudonym(answer["student_id"]),
                        }
                        for answer in poll.answers
                    ],
                }
            )
        snapshot = {
            "room_id": room.id,
            "title": room.title,
            "transcript": clean(room.transcript),
            "polls": polls,
            "comments": [
                {
                    "id": comment.id,
                    "pseudonym": pseudonym(comment.student_id),
                    "text": clean(comment.text),
                }
                for comment in room.comments
            ],
            "homework": [
                {
                    "id": item.id,
                    "pseudonym": pseudonym(item.student_id),
                    "text": clean(item.text),
                }
                for item in room.homework
            ],
            "attention": attention,
        }
        return snapshot, names, student_ids
