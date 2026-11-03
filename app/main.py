"""FastAPI entrypoint for the ZooMoodle demo."""

from __future__ import annotations

import base64
import hmac
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.attendance import CheckInError
from app.config import Settings
from app.export_svc import ExportService
from app.llm.agent import AgentError, HomeworkReviewService, SummaryService
from app.llm.providers import LLMClient, LLMConfig, ProviderFailure, build_provider
from app.net import client_ip, subnet_status
from app.store import Store, StoreError

STATIC_DIR = Path(__file__).resolve().parent / "static"
NOT_CONFIGURED = (
    "No LLM API key is configured. On the lecturer page, choose a provider, "
    "enter a key, and press Test connection. No model was called."
)
EXPORTS = ExportService()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    _announce(settings)
    app = FastAPI(title="ZooMoodle")
    app.state.settings = settings
    app.state.store = Store(settings)
    app.state.http_transport = None
    app.state.provider_factory = None

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "ephemeral_master_secret": settings.ephemeral_master_secret,
            "llm_configured": _llm_ready(app.state.store.llm),
        }

    @app.get("/")
    def lecturer_page():
        return FileResponse(STATIC_DIR / "lecturer.html")

    @app.get("/student")
    def student_page():
        return FileResponse(STATIC_DIR / "student.html")

    @app.post("/api/rooms")
    async def create_room(request: Request):
        _require_lecturer(request)
        body = await _json(request)
        room = app.state.store.create_room(str(body.get("title") or ""))
        return {"id": room.id, "title": room.title, "student_path": f"/student?room={room.id}"}

    @app.get("/api/rooms/{room_id}")
    def public_room(room_id: str):
        room = _room(app, room_id)
        return {"id": room.id, "title": room.title}

    @app.get("/api/rooms/{room_id}/token")
    def current_token(room_id: str, request: Request):
        _require_lecturer(request)
        store = app.state.store
        token = store.current_token(room_id)
        now = store.tokens.now()
        window_end = (token.window + 1) * store.tokens.window_seconds
        return {
            "code": token.code,
            "payload_hex": token.payload.hex(),
            "window": token.window,
            "issued_at": token.issued_at,
            "seconds_left": round(max(0.0, window_end - now), 2),
        }

    @app.post("/api/rooms/{room_id}/challenge")
    async def challenge(room_id: str, request: Request):
        body = await _json(request)
        room = _room(app, room_id)
        try:
            opened = room.attendance.open_challenge(
                str(body.get("student_id") or ""),
                str(body.get("device_id") or ""),
                body.get("public_jwk") or {},
                room.attendance.tokens.now(),
            )
        except CheckInError as exc:
            raise StoreError(exc.reason, 400) from exc
        return {"challenge_id": opened.id, "nonce": opened.nonce, "expires_in": settings.challenge_max_age_seconds}

    @app.post("/api/rooms/{room_id}/checkin")
    async def checkin(room_id: str, request: Request):
        body = await _json(request)
        room = _room(app, room_id)
        try:
            signature = _decode_signature(str(body.get("signature") or ""))
        except Exception as exc:
            raise StoreError("bad_signature", 400) from exc
        ip = client_ip(dict(request.headers), request.client.host if request.client else None)
        subnet = "not_applicable"
        mode = str(body.get("mode") or "")
        if mode == "in_class":
            subnet = subnet_status(ip, settings.allowed_subnets)
        try:
            outcome = room.attendance.check_in(
                challenge_id=str(body.get("challenge_id") or ""),
                signature=signature,
                mode=mode,
                token_code=body.get("token_code"),
                seat_zone=str(body.get("seat_zone") or ""),
                subnet=subnet,
                room_key=room.key,
                room_id=room.id,
                student_name=str(body.get("student_name") or ""),
                now=room.attendance.tokens.now(),
            )
        except CheckInError as exc:
            raise StoreError(exc.reason, 400) from exc
        record = outcome.record
        if record.student_name:
            room.names[record.student_id] = record.student_name
        payload = {
            "ok": True,
            "mode": record.mode,
            "confidence": record.confidence,
            "flags": list(record.flags),
            "seat_zone": record.seat_zone,
            "subnet": record.subnet,
        }
        if record.external_token:
            payload["external_token"] = record.external_token
        return payload

    @app.get("/api/rooms/{room_id}/attendance")
    def attendance(room_id: str, request: Request):
        _require_lecturer(request)
        room = _room(app, room_id)
        return {"records": [_record_dict(record) for record in room.attendance.records]}

    @app.get("/api/rooms/{room_id}/export.csv")
    def export_csv(room_id: str, request: Request):
        _require_lecturer(request)
        room = _room(app, room_id)
        data = EXPORTS.to_csv(room.attendance.records)
        return Response(
            content=data,
            media_type="text/csv",
            headers={"content-disposition": f'attachment; filename="{room.id}-attendance.csv"'},
        )

    @app.get("/api/rooms/{room_id}/export.xlsx")
    def export_xlsx(room_id: str, request: Request):
        _require_lecturer(request)
        room = _room(app, room_id)
        data = EXPORTS.to_xlsx(room.attendance.records)
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"content-disposition": f'attachment; filename="{room.id}-attendance.xlsx"'},
        )

    @app.post("/api/rooms/{room_id}/polls")
    async def create_poll(room_id: str, request: Request):
        _require_lecturer(request)
        body = await _json(request)
        poll = app.state.store.add_poll(
            room_id,
            str(body.get("question") or ""),
            list(body.get("options") or []),
            body.get("correct_option"),
        )
        return _poll_dict(poll, lecturer=True)

    @app.get("/api/rooms/{room_id}/polls")
    def list_polls(room_id: str, request: Request):
        room = _room(app, room_id)
        lecturer = _lecturer_ok(request)
        return {"polls": [_poll_dict(poll, lecturer=lecturer) for poll in room.polls]}

    @app.post("/api/rooms/{room_id}/polls/{poll_id}/answers")
    async def answer_poll(room_id: str, poll_id: str, request: Request):
        body = await _json(request)
        app.state.store.answer_poll(
            room_id,
            poll_id,
            str(body.get("student_id") or ""),
            str(body.get("option") or ""),
            str(body.get("seat_zone") or ""),
        )
        return {"ok": True}

    @app.post("/api/rooms/{room_id}/comments")
    async def add_comment(room_id: str, request: Request):
        body = await _json(request)
        comment = app.state.store.add_comment(
            room_id,
            str(body.get("student_id") or ""),
            str(body.get("student_name") or ""),
            str(body.get("text") or ""),
        )
        return {"id": comment.id}

    @app.get("/api/rooms/{room_id}/comments")
    def list_comments(room_id: str, request: Request):
        _require_lecturer(request)
        room = _room(app, room_id)
        return {
            "comments": [
                {
                    "id": comment.id,
                    "student_id": comment.student_id,
                    "name": room.names.get(comment.student_id, ""),
                    "text": comment.text,
                    "at": comment.at,
                }
                for comment in room.comments
            ]
        }

    @app.post("/api/rooms/{room_id}/homework")
    async def add_homework(room_id: str, request: Request):
        body = await _json(request)
        item = app.state.store.add_homework(
            room_id,
            str(body.get("student_id") or ""),
            str(body.get("student_name") or ""),
            str(body.get("text") or ""),
        )
        return {"id": item.id}

    @app.get("/api/rooms/{room_id}/homework")
    def list_homework(room_id: str, request: Request):
        _require_lecturer(request)
        room = _room(app, room_id)
        return {
            "submissions": [
                {
                    "id": item.id,
                    "student_id": item.student_id,
                    "name": room.names.get(item.student_id, ""),
                    "characters": len(item.text),
                    "at": item.at,
                }
                for item in room.homework
            ]
        }

    @app.post("/api/rooms/{room_id}/transcript")
    async def upload_transcript(room_id: str, request: Request):
        _require_lecturer(request)
        text = await _transcript_text(request)
        count = app.state.store.set_transcript(room_id, text)
        return {"characters": count}

    @app.post("/api/rooms/{room_id}/agent/summary")
    async def agent_summary(room_id: str, request: Request):
        _require_lecturer(request)
        _require_llm(app)
        store = app.state.store
        snapshot, names, student_ids = store.snapshot(room_id)
        service = SummaryService(_client_factory(app), settings.agent_max_steps)
        try:
            return service.summarize(snapshot, names, student_ids)
        except (AgentError, ProviderFailure) as exc:
            raise StoreError(getattr(exc, "message", str(exc)), 502) from exc

    @app.post("/api/rooms/{room_id}/agent/homework")
    async def agent_homework(room_id: str, request: Request):
        body = await _json(request)
        audience = str(body.get("audience") or "")
        if audience == "lecturer":
            _require_lecturer(request)
        elif audience != "student":
            raise StoreError("audience must be student or lecturer.", 400)
        _require_llm(app)
        submission_id = str(body.get("submission_id") or "")
        room = _room(app, room_id)
        if not any(item.id == submission_id for item in room.homework):
            raise StoreError("unknown_submission", 404)
        snapshot, names, student_ids = app.state.store.snapshot(room_id)
        service = HomeworkReviewService(_client_factory(app), settings.agent_max_steps)
        try:
            return service.review(snapshot, submission_id, audience, names, student_ids)
        except (AgentError, ProviderFailure) as exc:
            raise StoreError(getattr(exc, "message", str(exc)), 502) from exc

    @app.post("/api/rooms/{room_id}/attention/samples")
    async def attention_samples(room_id: str, request: Request):
        _require_lecturer(request)
        body = await _json(request)
        room = _room(app, room_id)
        samples = body.get("samples") or []
        if not isinstance(samples, list) or not samples:
            raise StoreError("samples_required", 400)
        try:
            for sample in samples:
                room.attention.add_sample(
                    float(sample["t_seconds"]),
                    str(sample["zone"]),
                    float(sample["level"]),
                    str(sample.get("source") or ""),
                )
        except (KeyError, TypeError, ValueError) as exc:
            raise StoreError(str(exc), 400) from exc
        return room.attention.by_zone()

    @app.get("/api/rooms/{room_id}/attention")
    def attention(room_id: str, request: Request):
        _require_lecturer(request)
        room = _room(app, room_id)
        view = room.attention.by_zone()
        view.pop("samples", None)
        return view

    @app.get("/api/llm/config")
    def llm_config(request: Request):
        _require_lecturer(request)
        return _public_llm(app.state.store.llm)

    @app.post("/api/llm/config")
    async def save_llm_config(request: Request):
        _require_lecturer(request)
        body = await _json(request)
        current = app.state.store.llm
        provider = str(body.get("provider") if body.get("provider") is not None else current.provider)
        model = str(body.get("model") if body.get("model") is not None else current.model)
        base_url = str(body.get("base_url") if body.get("base_url") is not None else current.base_url)
        api_key = current.api_key
        if body.get("clear_key"):
            api_key = ""
        elif str(body.get("api_key") or "").strip():
            api_key = str(body.get("api_key")).strip()
        timeout = current.timeout_seconds
        if body.get("timeout_seconds") is not None:
            try:
                timeout = float(body["timeout_seconds"])
            except (TypeError, ValueError):
                raise StoreError("bad_timeout", 400)
        app.state.store.llm = LLMConfig(
            provider=provider.strip(),
            model=model.strip(),
            base_url=base_url.strip(),
            api_key=api_key,
            timeout_seconds=timeout,
        )
        return _public_llm(app.state.store.llm)

    @app.post("/api/llm/test")
    async def llm_test(request: Request):
        _require_lecturer(request)
        body = await _json(request)
        saved = app.state.store.llm
        api_key = str(body.get("api_key") or "").strip() or saved.api_key
        config = LLMConfig(
            provider=str(body.get("provider") or saved.provider),
            model=str(body.get("model") or saved.model),
            base_url=str(body.get("base_url") if body.get("base_url") is not None else saved.base_url),
            api_key=api_key,
            timeout_seconds=saved.timeout_seconds,
        )
        try:
            client = LLMClient(_make_provider(app, config))
            result = client.test_connection()
        except ProviderFailure as exc:
            from app.llm.providers import ConnectResult

            result = ConnectResult(
                status="error",
                provider=config.provider.strip().lower(),
                model=config.model.strip(),
                latency_ms=0,
                tool_calling="not_checked",
                category=exc.category,
                message=exc.message,
            )
        payload = result.as_dict()
        if api_key and api_key in str(payload):
            # Belt and braces: never echo a key even if a provider message slipped.
            payload["message"] = str(payload["message"]).replace(api_key, "[redacted]")
        return payload

    @app.exception_handler(StoreError)
    async def store_error(_request: Request, exc: StoreError):
        return JSONResponse(status_code=exc.status, content={"error": exc.reason})

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def _announce(settings: Settings) -> None:
    if "pytest" in sys.modules or getattr(_announce, "done", False):
        return
    _announce.done = True
    if settings.generated_lecturer_token:
        print(f"Lecturer token for this run: {settings.lecturer_token}", flush=True)
    if settings.ephemeral_master_secret:
        print(
            "ZOOMODLE_MASTER_SECRET is unset. This process is using an ephemeral secret; "
            "rooms will not verify after a restart.",
            flush=True,
        )


def _lecturer_ok(request: Request) -> bool:
    provided = request.headers.get("x-lecturer-token", "")
    expected = request.app.state.settings.lecturer_token
    if len(provided) != len(expected):
        return False
    return hmac.compare_digest(provided, expected)


def _require_lecturer(request: Request) -> None:
    if not _lecturer_ok(request):
        raise StoreError("Lecturer token was rejected.", 401)


def _room(app: FastAPI, room_id: str):
    return app.state.store.get(room_id)


def _llm_ready(config: LLMConfig) -> bool:
    name = config.provider.strip().lower()
    if name not in ("openai", "anthropic", "gemini", "xai", "ollama", "openai_compatible"):
        return False
    if not config.model.strip():
        return False
    if name == "openai_compatible" and not config.base_url.strip():
        return False
    if name not in ("ollama", "openai_compatible") and not config.api_key:
        return False
    return True


def _require_llm(app: FastAPI) -> None:
    if not _llm_ready(app.state.store.llm):
        raise StoreError(NOT_CONFIGURED, 503)


def _make_provider(app: FastAPI, config: LLMConfig):
    factory = app.state.provider_factory
    if factory is not None:
        return factory(config)
    return build_provider(config, app.state.http_transport)


def _client_factory(app: FastAPI):
    def factory():
        return LLMClient(_make_provider(app, app.state.store.llm))

    return factory


def _public_llm(config: LLMConfig) -> dict:
    return {
        "provider": config.provider,
        "model": config.model,
        "base_url": config.base_url,
        "timeout_seconds": config.timeout_seconds,
        "key_configured": bool(config.api_key),
        "ready": _llm_ready(config),
    }


async def _json(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception as exc:
        raise StoreError("expected_json", 400) from exc
    if not isinstance(body, dict):
        raise StoreError("expected_json", 400)
    return body


async def _transcript_text(request: Request) -> str:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        if upload is not None and hasattr(upload, "read"):
            raw = await upload.read()
            return raw.decode("utf-8", errors="replace")
        return str(form.get("transcript") or "")
    body = await _json(request)
    return str(body.get("transcript") or "")


def _decode_signature(text: str) -> bytes:
    raw = "".join(text.split())
    pad = "=" * ((4 - len(raw) % 4) % 4)
    try:
        return base64.b64decode(raw + pad)
    except Exception:
        return base64.urlsafe_b64decode(raw + pad)


def _record_dict(record) -> dict:
    return {
        "student_id": record.student_id,
        "name": record.student_name,
        "device_id": record.device_id,
        "mode": record.mode,
        "seat_zone": record.seat_zone,
        "at": record.at,
        "confidence": record.confidence,
        "flags": list(record.flags),
        "subnet": record.subnet,
    }


def _poll_dict(poll, lecturer: bool) -> dict:
    counts: dict[str, int] = {}
    by_zone: dict[str, dict[str, int]] = {}
    for answer in poll.answers:
        counts[answer["option"]] = counts.get(answer["option"], 0) + 1
        zone = by_zone.setdefault(answer["seat_zone"], {})
        zone[answer["option"]] = zone.get(answer["option"], 0) + 1
    payload = {
        "id": poll.id,
        "question": poll.question,
        "options": list(poll.options),
        "answer_count": len(poll.answers),
    }
    if lecturer:
        payload["correct_option"] = poll.correct_option
        payload["counts"] = counts
        payload["by_zone"] = by_zone
    return payload


app = create_app()


def main() -> None:
    import uvicorn

    settings = app.state.settings
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
