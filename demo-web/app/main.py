"""FastAPI entrypoint for the ZooMoodle demo."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.checkin import ACTIVE_STATES, CONFLICT_STATES, PRESENT, REJECTED, REMOTE, CheckinError
from app.config import Settings
from app.export_svc import ExportService
from app.lecturer_auth import LecturerAuth, LecturerAuthError
from app.llm.agent import AgentError, SummaryService
from app.llm.providers import KEY_OPTIONAL, KNOWN_PROVIDERS, LLMClient, LLMConfig, ProviderFailure, build_provider
from app.mailer import Mailer
from app.net import client_ip, subnet_status
from app.roster import RosterError
from app.session_keys import SessionError, canonical_message
from app.store import Store, StoreError

STATIC_DIR = Path(__file__).resolve().parent / "static"
DIAGRAM_DIR = Path(__file__).resolve().parents[2] / "docs" / "diagrams"
EXPORTS = ExportService()
STATE_TEXT = {
    "remote": "מחובר מרחוק",
    "pending_barcode": "ממתין לסריקת הברקוד החי",
    "needs_area": "ממתין לבחירת אזור בכיתה",
    "present": "נוכח בכיתה",
    "flagged_remote": "בבדיקה: השם נבחר גם במקום אחר",
    "repick": "צריך לבחור שוב את השם",
    "email_code": "ממתין לקוד מהמייל",
    "lecturer_decision": "המרצה יחליט",
    "rejected": "נדחה",
}


def create_app(settings: Settings | None = None, mailer: Mailer | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    _announce(settings)
    app = FastAPI(title="ZooMoodle")
    app.state.settings = settings
    app.state.store = Store(settings, mailer)
    app.state.auth = LecturerAuth(settings.master_secret, settings.lecturer_key)
    app.state.http_transport = None
    app.state.provider_factory = None

    def lecturer(request: Request) -> None:
        if not app.state.auth.check(request.headers.get("x-lecturer-session", "")):
            raise StoreError("lecturer_required", 401)

    def is_lecturer(request: Request) -> bool:
        return app.state.auth.check(request.headers.get("x-lecturer-session", ""))

    def room_of(room_id: str):
        return app.state.store.get(room_id)

    def open_room(room_id: str):
        room = room_of(room_id)
        if room.closed:
            raise StoreError("room_closed", 409)
        return room

    def on_campus(request: Request) -> bool:
        ip = client_ip(dict(request.headers), request.client.host if request.client else None, settings.trusted_proxies)
        return subnet_status(ip, settings.campus_ranges) == "match"

    def claim_for(room, session):
        try:
            return room.checkin.get(session.student_id)
        except CheckinError as exc:
            raise StoreError("session_mismatch", 401) from exc

    def active_claim(request: Request, room, raw: bytes, write: bool):
        claim = claim_for(room, _require_session(request, room, raw, write=write))
        if claim.state not in ACTIVE_STATES:
            raise StoreError("not_checked_in", 403)
        return claim

    # ----- pages ---------------------------------------------------------
    @app.get("/api/health")
    def health():
        return {"status": "ok", "ephemeral_master_secret": settings.ephemeral_master_secret}

    @app.get("/")
    def lecturer_page():
        return FileResponse(STATIC_DIR / "lecturer.html")

    @app.get("/student")
    def student_page():
        return FileResponse(STATIC_DIR / "student.html")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(STATIC_DIR / "favicon.ico", media_type="image/x-icon")

    # ----- lecturer sign-in ----------------------------------------------
    @app.post("/api/lecturer/login")
    async def lecturer_login(request: Request):
        body = await _json(request)
        try:
            token = app.state.auth.sign_in(str(body.get("key") or ""))
        except LecturerAuthError as exc:
            raise StoreError(exc.reason, exc.status) from exc
        return {"token": token, **_profile(settings)}

    @app.get("/api/lecturer/me")
    def lecturer_me(request: Request):
        lecturer(request)
        return _profile(settings)

    @app.post("/api/lecturer/logout")
    def lecturer_logout(request: Request):
        app.state.auth.sign_out(request.headers.get("x-lecturer-session", ""))
        return {"ok": True}

    # ----- rooms -------------------------------------------------------------
    @app.post("/api/rooms")
    async def create_room(request: Request):
        lecturer(request)
        body = await _json(request)
        return _room_link(request, app.state.store.create_room(str(body.get("title") or "")))

    @app.get("/api/rooms")
    def list_rooms(request: Request):
        lecturer(request)
        return {"rooms": [_room_link(request, r) for r in app.state.store.rooms.values() if not r.closed]}

    @app.get("/api/rooms/{room_id}")
    def public_room(room_id: str, request: Request):
        room = room_of(room_id)
        return {
            "id": room.id,
            "title": room.title,
            "closed": room.closed,
            "course": settings.course_name,
            "week": settings.course_week,
            **room.screen_qr.public_params(),
        }

    @app.post("/api/rooms/{room_id}/close")
    def close_room(room_id: str, request: Request):
        lecturer(request)
        room = app.state.store.close_room(room_id)
        room.sessions.revoke_all()
        return {"id": room.id, "closed": True}

    @app.post("/api/rooms/{room_id}/roster")
    async def upload_roster(room_id: str, request: Request):
        lecturer(request)
        room = room_of(room_id)
        text = await _upload_text(request, "text")
        if len(text) > 1_000_000:
            raise StoreError("roster_too_large", 400)
        try:
            return room.roster.replace_from_csv(text)
        except RosterError as exc:
            raise StoreError(exc.reason, 400) from exc

    @app.post("/api/rooms/{room_id}/roster/group")
    async def select_group(room_id: str, request: Request):
        lecturer(request)
        room = room_of(room_id)
        body = await _json(request)
        if body.get("all"):
            room.roster.selected_group = None
            room.roster.include_unspecified = False
            return {"group": "", "listed": len(room.roster.public_names())}
        try:
            return room.roster.select_group(body.get("group"), bool(body.get("include_unspecified")))
        except RosterError as exc:
            raise StoreError(exc.reason, 400) from exc

    @app.get("/api/rooms/{room_id}/roster/names")
    def roster_names(room_id: str):
        return {"names": open_room(room_id).roster.public_names()}

    # ----- live barcode -------------------------------------------------------
    @app.get("/api/rooms/{room_id}/barcode")
    def barcode(room_id: str, request: Request):
        lecturer(request)
        room = open_room(room_id)
        frame = room.screen_qr.issue(room.key, room.id)
        return {
            "code": frame.code,
            "slot": frame.slot,
            "expires_in": round(frame.expires_in, 3),
            "flicker_seed": room.screen_qr.flicker_seed(room.key, room.id),
            **room.screen_qr.public_params(),
        }

    # ----- student check-in ---------------------------------------------------
    @app.post("/api/rooms/{room_id}/join")
    async def join(room_id: str, request: Request):
        room = open_room(room_id)
        body = await _json(request)
        mode = str(body.get("mode") or "")
        try:
            claim = room.checkin.join(str(body.get("entry_id") or ""), mode, mode == "in_class" and on_campus(request))
        except CheckinError as exc:
            raise StoreError(exc.reason, exc.status) from exc
        session_id, session_key = room.sessions.issue(claim.id)
        return {"session_id": session_id, "session_key": session_key, **_me(room, claim)}

    @app.get("/api/rooms/{room_id}/me")
    async def me(room_id: str, request: Request):
        room = room_of(room_id)
        room.checkin.expire()
        claim = claim_for(room, _require_session(request, room, await request.body(), write=False))
        return _me(room, claim)

    @app.post("/api/rooms/{room_id}/barcode")
    async def submit_barcode(room_id: str, request: Request):
        raw = await request.body()
        room = open_room(room_id)
        claim = claim_for(room, _require_session(request, room, raw, write=True))
        body = _body_dict(raw)
        try:
            room.checkin.submit_barcode(claim, body.get("codes"), on_campus(request), room.key, room.id)
        except CheckinError as exc:
            raise StoreError(exc.reason, exc.status) from exc
        return _me(room, claim)

    @app.post("/api/rooms/{room_id}/area")
    async def choose_area(room_id: str, request: Request):
        raw = await request.body()
        room = open_room(room_id)
        claim = claim_for(room, _require_session(request, room, raw, write=True))
        try:
            room.checkin.choose_area(claim, str(_body_dict(raw).get("zone") or ""))
        except CheckinError as exc:
            raise StoreError(exc.reason, exc.status) from exc
        return _me(room, claim)

    @app.post("/api/rooms/{room_id}/repick")
    async def repick(room_id: str, request: Request):
        raw = await request.body()
        room = open_room(room_id)
        claim = claim_for(room, _require_session(request, room, raw, write=True))
        try:
            room.checkin.repick(claim, str(_body_dict(raw).get("entry_id") or ""))
        except CheckinError as exc:
            raise StoreError(exc.reason, exc.status) from exc
        return _me(room, claim)

    @app.post("/api/rooms/{room_id}/email-code")
    async def email_code(room_id: str, request: Request):
        raw = await request.body()
        room = open_room(room_id)
        claim = claim_for(room, _require_session(request, room, raw, write=True))
        try:
            room.checkin.submit_code(claim, str(_body_dict(raw).get("code") or ""))
        except CheckinError as exc:
            raise StoreError(exc.reason, exc.status) from exc
        return _me(room, claim)

    # ----- lecturer dashboard ---------------------------------------------------
    @app.get("/api/rooms/{room_id}/dashboard")
    def dashboard(room_id: str, request: Request):
        lecturer(request)
        room = room_of(room_id)
        room.checkin.expire()
        return {
            **_room_link(request, room),
            "greeting": settings.greeting,
            "counts": room.checkin.counts(),
            "zones": room.checkin.zone_counts(),
            "roster_size": len(room.roster.public_names()),
            "students": _students(room),
            "conflicts": _conflicts(room),
            "comments": [
                {"id": c.id, "name": _name_of(room, c.student_id), "text": c.text, "at": c.at} for c in room.comments
            ],
            "questions": [
                {"id": q.id, "name": _name_of(room, q.student_id), "text": q.text, "votes": len(q.upvotes)}
                for q in app.state.store.questions_by_votes(room)
            ],
            "polls": [_poll_dict(p, lecturer=True) for p in room.polls],
            "homework": [_homework_dict(h) for h in room.homework],
            "summary": room.summary,
            "summary_source": room.summary_source,
            "email_mode": "smtp" if app.state.store.mailer.configured else "demo",
        }

    @app.post("/api/rooms/{room_id}/conflicts/decide")
    async def decide(room_id: str, request: Request):
        lecturer(request)
        room = room_of(room_id)
        body = await _json(request)
        try:
            claim = room.checkin.decide(str(body.get("claim_id") or ""), str(body.get("action") or ""))
        except CheckinError as exc:
            raise StoreError(exc.reason, exc.status) from exc
        return {"claim_id": claim.id, "state": claim.state}

    @app.get("/api/rooms/{room_id}/export.csv")
    def export_csv(room_id: str, request: Request):
        lecturer(request)
        room = room_of(room_id)
        return Response(
            EXPORTS.to_csv(_students(room)),
            media_type="text/csv",
            headers={"content-disposition": f'attachment; filename="{room.id}-attendance.csv"'},
        )

    @app.get("/api/rooms/{room_id}/export.xlsx")
    def export_xlsx(room_id: str, request: Request):
        lecturer(request)
        room = room_of(room_id)
        return Response(
            EXPORTS.to_xlsx(_students(room)),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"content-disposition": f'attachment; filename="{room.id}-attendance.xlsx"'},
        )

    # ----- polls, notes, questions ----------------------------------------------
    @app.post("/api/rooms/{room_id}/polls")
    async def create_poll(room_id: str, request: Request):
        lecturer(request)
        room = open_room(room_id)
        body = await _json(request)
        poll = app.state.store.add_poll(room, str(body.get("question") or ""), list(body.get("options") or []), body.get("correct_option"))
        return _poll_dict(poll, lecturer=True)

    @app.post("/api/rooms/{room_id}/polls/{poll_id}/close")
    def close_poll(room_id: str, poll_id: str, request: Request):
        lecturer(request)
        room = room_of(room_id)
        poll = next((p for p in room.polls if p.id == poll_id), None)
        if poll is None:
            raise StoreError("unknown_poll", 404)
        poll.open = False
        return _poll_dict(poll, lecturer=True)

    @app.get("/api/rooms/{room_id}/polls")
    async def list_polls(room_id: str, request: Request):
        room = room_of(room_id)
        claim = claim_for(room, _require_session(request, room, await request.body(), write=False))
        return {"polls": [_poll_dict(p, lecturer=False, student_id=claim.id) for p in room.polls]}

    @app.post("/api/rooms/{room_id}/polls/{poll_id}/answers")
    async def answer_poll(room_id: str, poll_id: str, request: Request):
        raw = await request.body()
        room = open_room(room_id)
        claim = active_claim(request, room, raw, write=True)
        option = str(_body_dict(raw).get("option") or "")
        zone = "remote" if claim.state == REMOTE else claim.zone
        poll = app.state.store.answer_poll(room, poll_id, claim.id, option, zone)
        return {"ok": True, "voted_option": option, "counts": _option_counts(poll)}

    @app.post("/api/rooms/{room_id}/comments")
    async def add_comment(room_id: str, request: Request):
        raw = await request.body()
        room = open_room(room_id)
        claim = active_claim(request, room, raw, write=True)
        comment = app.state.store.add_comment(room, claim.id, str(_body_dict(raw).get("text") or ""))
        return {"id": comment.id}

    @app.get("/api/rooms/{room_id}/questions")
    async def list_questions(room_id: str, request: Request):
        room = room_of(room_id)
        claim = claim_for(room, _require_session(request, room, await request.body(), write=False))
        return {
            "questions": [
                {"id": q.id, "text": q.text, "votes": len(q.upvotes), "upvoted": claim.id in q.upvotes}
                for q in app.state.store.questions_by_votes(room)
            ]
        }

    @app.post("/api/rooms/{room_id}/questions")
    async def add_question(room_id: str, request: Request):
        raw = await request.body()
        room = open_room(room_id)
        claim = active_claim(request, room, raw, write=True)
        question = app.state.store.add_question(room, claim.id, str(_body_dict(raw).get("text") or ""))
        return {"id": question.id}

    @app.post("/api/rooms/{room_id}/questions/{question_id}/upvote")
    async def upvote(room_id: str, question_id: str, request: Request):
        raw = await request.body()
        room = open_room(room_id)
        claim = active_claim(request, room, raw, write=True)
        question = app.state.store.upvote_question(room, question_id, claim.id)
        return {"id": question.id, "votes": len(question.upvotes), "upvoted": True}

    # ----- homework files ---------------------------------------------------------
    @app.post("/api/rooms/{room_id}/homework")
    async def upload_homework(room_id: str, request: Request):
        lecturer(request)
        room = room_of(room_id)
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise StoreError("missing_file")
        data = await upload.read()
        item = app.state.store.add_homework(
            room, str(form.get("title") or ""), upload.filename or "", upload.content_type or "", data
        )
        return _homework_dict(item)

    @app.get("/api/rooms/{room_id}/homework")
    async def list_homework(room_id: str, request: Request):
        room = room_of(room_id)
        if not is_lecturer(request):
            _viewer(request, room, await request.body())
        return {"homework": [_homework_dict(h) for h in room.homework]}

    @app.get("/api/rooms/{room_id}/homework/{homework_id}")
    async def download_homework(room_id: str, homework_id: str, request: Request):
        room = room_of(room_id)
        if not is_lecturer(request):
            _viewer(request, room, await request.body())
        item = next((h for h in room.homework if h.id == homework_id), None)
        if item is None:
            raise StoreError("unknown_homework", 404)
        return Response(
            item.data,
            media_type="application/octet-stream",
            headers={
                "content-disposition": "attachment; filename*=UTF-8''" + _quote(item.filename),
                "x-content-type-options": "nosniff",
            },
        )

    # ----- lesson summary -----------------------------------------------------------
    @app.post("/api/rooms/{room_id}/transcript")
    async def upload_transcript(room_id: str, request: Request):
        lecturer(request)
        room = room_of(room_id)
        room.transcript = (await _upload_text(request, "transcript"))[:200000]
        return {"characters": len(room.transcript)}

    @app.post("/api/rooms/{room_id}/summary")
    async def publish_summary(room_id: str, request: Request):
        lecturer(request)
        room = room_of(room_id)
        text = str((await _json(request)).get("text") or "").strip()[:20000]
        if not text:
            raise StoreError("missing_summary")
        room.summary, room.summary_source = text, "lecturer"
        return {"published": True, "text": text}

    @app.get("/api/rooms/{room_id}/summary")
    async def read_summary(room_id: str, request: Request):
        room = room_of(room_id)
        if not is_lecturer(request):
            _viewer(request, room, await request.body())
        return {"text": room.summary, "source": room.summary_source}

    @app.post("/api/rooms/{room_id}/summary/generate")
    async def generate_summary(room_id: str, request: Request):
        raw = await request.body()
        room = room_of(room_id)
        by_lecturer = is_lecturer(request)
        if not by_lecturer:
            _viewer(request, room, raw)
        body = _body_dict(raw)
        api_key = str(body.get("api_key") or "").strip()
        config = LLMConfig(
            provider=str(body.get("provider") or "openai").strip().lower(),
            model=str(body.get("model") or "").strip(),
            base_url=str(body.get("base_url") or "").strip(),
            api_key=api_key,
            timeout_seconds=settings.llm_timeout_seconds,
        )
        del body, raw
        if config.provider not in KNOWN_PROVIDERS:
            raise StoreError("unknown_provider", 400)
        if not config.model:
            raise StoreError("missing_model", 400)
        if config.provider not in KEY_OPTIONAL and not api_key:
            raise StoreError("missing_key", 400)
        snapshot, names, ids = app.state.store.snapshot(room)
        provider = (app.state.provider_factory or (lambda c: build_provider(c, app.state.http_transport)))(config)
        service = SummaryService(lambda: LLMClient(provider), settings.agent_max_steps)
        try:
            report = service.summarize(snapshot, names, ids)["report"]
        except (AgentError, ProviderFailure) as exc:
            message = str(getattr(exc, "message", "") or "model_failed")
            if api_key:
                message = message.replace(api_key, "[redacted]")
            raise StoreError(message, 502) from None
        finally:
            config.api_key = ""
            del provider, config, api_key
        text = _summary_text(report)
        if by_lecturer:
            room.summary, room.summary_source = text, "model"
        return {"text": text, "published": by_lecturer}

    # ----- misc ---------------------------------------------------------------------
    @app.get("/api/diagrams")
    def diagrams():
        if not DIAGRAM_DIR.is_dir():
            return {"diagrams": []}
        return {"diagrams": [{"file": p.name, "src": f"/diagrams/{p.name}"} for p in sorted(DIAGRAM_DIR.glob("*.svg"))]}

    @app.exception_handler(StoreError)
    async def store_error(_request: Request, exc: StoreError):
        return JSONResponse(status_code=exc.status, content={"error": exc.reason})

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    if DIAGRAM_DIR.is_dir():
        app.mount("/diagrams", StaticFiles(directory=DIAGRAM_DIR), name="diagrams")
    return app


# ----- helpers ------------------------------------------------------------------
def _announce(settings: Settings) -> None:
    if "pytest" in sys.modules or getattr(_announce, "done", False):
        return
    _announce.done = True
    if settings.lecturer_key_file:
        verb = "Created" if settings.lecturer_key_created else "Using"
        print(f"{verb} lecturer key file: {settings.lecturer_key_file} (the key itself is not printed)", flush=True)
    if settings.ephemeral_master_secret:
        print("ZOOMODLE_MASTER_SECRET is unset; rooms will not survive a restart.", flush=True)
    if not settings.smtp_configured:
        print("SMTP is not configured: duplicate-name codes are shown on the lecturer dashboard (demo mode).", flush=True)


def _profile(settings: Settings) -> dict:
    return {
        "greeting": settings.greeting,
        "lecturer_name": settings.lecturer_name,
        "course": settings.course_name,
        "week": settings.course_week,
    }


_ORIGIN = re.compile(r"^https?://[A-Za-z0-9._:-]+(?::\d+)?$")


def _public_origin(request: Request) -> str:
    for name in ("ZOOMODLE_PUBLIC_ORIGIN", "ZOOMODLE_PUBLIC_BASE_URL", "RENDER_EXTERNAL_URL"):
        raw = os.environ.get(name, "").strip().rstrip("/")
        if _ORIGIN.match(raw):
            return raw
    base = str(request.base_url).rstrip("/")
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if proto in ("https", "http") and "://" in base:
        return proto + "://" + base.split("://", 1)[1]
    return base


def _room_link(request: Request, room) -> dict:
    path = f"/student?room={room.id}"
    return {
        "id": room.id,
        "title": room.title,
        "closed": room.closed,
        "student_path": path,
        "student_url": _public_origin(request) + path,
    }


def _name_of(room, claim_id: str) -> str:
    claim = room.checkin.claims.get(claim_id)
    entry = room.roster.entries.get(claim.entry_id) if claim else None
    return entry.display if entry else ""


def _me(room, claim) -> dict:
    entry = room.roster.entries.get(claim.entry_id)
    display = entry.display if entry else ""
    view = {
        "claim_id": claim.id,
        "display": display,
        "mode": claim.mode,
        "state": claim.state,
        "state_text": STATE_TEXT.get(claim.state, claim.state),
        "zone": claim.zone,
        "checked": claim.state in (PRESENT, REMOTE),
    }
    if claim.state in (PRESENT, REMOTE):
        view["welcome"] = f"ברוך הבא {display}"
    if claim.state == "email_code":
        challenge = room.checkin.challenge_view(claim.entry_id)
        view["email_sent"] = bool(challenge and challenge["sent"])
    return view


def _students(room) -> list[dict]:
    rows = []
    for claim in sorted(room.checkin.claims.values(), key=lambda c: c.at):
        rows.append(
            {
                "claim_id": claim.id,
                "name": _name_of(room, claim.id),
                "mode": "בכיתה" if claim.mode == "in_class" else "מרחוק",
                "state": claim.state,
                "state_text": STATE_TEXT.get(claim.state, claim.state),
                "zone": claim.zone,
                "checked": claim.state in (PRESENT, REMOTE),
                "at": claim.at,
            }
        )
    return rows


def _conflicts(room) -> list[dict]:
    groups: dict[str, list] = {}
    for claim in room.checkin.claims.values():
        if claim.state in CONFLICT_STATES:
            groups.setdefault(claim.entry_id, [])
    out = []
    for entry_id in groups:
        entry = room.roster.entries.get(entry_id)
        claims = [c for c in room.checkin.claims.values() if c.entry_id == entry_id and c.state != REJECTED]
        out.append(
            {
                "name": entry.display if entry else "",
                "claims": [
                    {
                        "claim_id": c.id,
                        "mode": c.mode,
                        "state": c.state,
                        "state_text": STATE_TEXT.get(c.state, c.state),
                        "zone": c.zone,
                        "note": c.note,
                    }
                    for c in claims
                ],
                "email": room.checkin.challenge_view(entry_id),
            }
        )
    return out


def _option_counts(poll) -> dict:
    counts = {option: 0 for option in poll.options}
    for answer in poll.answers:
        counts[answer["option"]] = counts.get(answer["option"], 0) + 1
    return counts


def _poll_dict(poll, lecturer: bool, student_id: str = "") -> dict:
    voted = next((a for a in poll.answers if student_id and a["student_id"] == student_id), None)
    payload = {
        "id": poll.id,
        "question": poll.question,
        "options": list(poll.options),
        "open": poll.open,
        "answer_count": len(poll.answers),
    }
    if lecturer or voted is not None or not poll.open:
        payload["counts"] = _option_counts(poll)
    if voted is not None:
        payload["voted_option"] = voted["option"]
    if lecturer:
        payload["correct_option"] = poll.correct_option
    return payload


def _homework_dict(item) -> dict:
    return {"id": item.id, "title": item.title, "filename": item.filename, "size": len(item.data), "at": item.at}


def _summary_text(report: dict) -> str:
    lines: list[str] = []

    def section(title: str, items) -> None:
        items = [i for i in (items or []) if i]
        if not items:
            return
        if lines:
            lines.append("")
        lines.append(title)
        for item in items:
            if isinstance(item, dict):
                item = item.get("title") or item.get("text") or item.get("finding") or json.dumps(item, ensure_ascii=False)
            lines.append("- " + str(item))

    section("נושאים", report.get("topics"))
    section("ממצאים", report.get("zone_findings"))
    section("המלצות לשיעור הבא", report.get("recommendations"))
    return "\n".join(lines) or json.dumps(report, ensure_ascii=False, indent=2)


def _quote(name: str) -> str:
    from urllib.parse import quote

    return quote(name, safe="")


async def _json(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception as exc:
        raise StoreError("expected_json", 400) from exc
    if not isinstance(body, dict):
        raise StoreError("expected_json", 400)
    return body


async def _upload_text(request: Request, field: str) -> str:
    if "multipart/form-data" in request.headers.get("content-type", ""):
        form = await request.form()
        upload = form.get("file")
        if upload is not None and hasattr(upload, "read"):
            return (await upload.read()).decode("utf-8-sig", errors="replace")
        return str(form.get(field) or "")
    return str((await _json(request)).get(field) or "")


def _body_dict(raw: bytes) -> dict:
    if not raw:
        return {}
    try:
        body = json.loads(raw)
    except Exception as exc:
        raise StoreError("expected_json", 400) from exc
    if not isinstance(body, dict):
        raise StoreError("expected_json", 400)
    return body


def _signed_target(request: Request) -> str:
    query = request.scope.get("query_string", b"").decode("ascii", errors="replace")
    return request.url.path + ("?" + query if query else "")


def _require_session(request: Request, room, raw: bytes, *, write: bool):
    try:
        return room.sessions.verify(
            session_id=request.headers.get("x-zoomoodle-session", ""),
            timestamp=request.headers.get("x-zoomoodle-timestamp", ""),
            nonce=request.headers.get("x-zoomoodle-nonce", ""),
            signature=request.headers.get("x-zoomoodle-signature", ""),
            message=canonical_message(
                request.method,
                _signed_target(request),
                raw,
                request.headers.get("x-zoomoodle-timestamp", ""),
                request.headers.get("x-zoomoodle-nonce", ""),
            ),
            write=write,
        )
    except SessionError as exc:
        raise StoreError(exc.reason, 401) from exc


def _viewer(request: Request, room, raw: bytes):
    session = _require_session(request, room, raw, write=False)
    claim = room.checkin.claims.get(session.student_id)
    if claim is None or claim.state == REJECTED:
        raise StoreError("not_checked_in", 403)
    return claim


app = create_app()


def main() -> None:
    import uvicorn

    settings = app.state.settings
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
