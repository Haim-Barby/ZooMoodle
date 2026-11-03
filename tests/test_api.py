import base64
import json

import httpx
from fastapi.testclient import TestClient

from app.llm.providers import LLMResponse, ToolCall
from app.main import NOT_CONFIGURED, create_app
from tests.conftest import make_device, make_settings

TOKEN = "lecturer-test-token"
SECRET = "sk-test-secret"


def _app():
    application = create_app(make_settings())
    return application, TestClient(application)


def _auth():
    return {"x-lecturer-token": TOKEN}


def test_health_and_lecturer_token_gate():
    _application, client = _app()
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert "api_key" not in health.text
    rejected = client.post("/api/rooms", json={"title": "Lesson"})
    assert rejected.status_code == 401


def test_checkin_export_and_hidden_poll_answer():
    _application, client = _app()
    room = client.post("/api/rooms", json={"title": "Lesson"}, headers=_auth()).json()
    room_id = room["id"]
    code = client.get(f"/api/rooms/{room_id}/token", headers=_auth()).json()["code"]
    stolen = client.get(f"/api/rooms/{room_id}/token")
    assert stolen.status_code == 401

    device = make_device()
    opened = client.post(
        f"/api/rooms/{room_id}/challenge",
        json={"student_id": "stu-1", "device_id": device["device_id"], "public_jwk": device["jwk"]},
    ).json()
    signature = base64.b64encode(device["sign"](opened["challenge_id"], opened["nonce"])).decode()
    checked = client.post(
        f"/api/rooms/{room_id}/checkin",
        json={
            "challenge_id": opened["challenge_id"],
            "signature": signature,
            "mode": "in_class",
            "token_code": code,
            "seat_zone": "front-left",
            "student_name": "Ada",
        },
    )
    assert checked.status_code == 200
    assert checked.json()["confidence"] == "high"

    sheet = client.get(f"/api/rooms/{room_id}/export.csv", headers=_auth())
    assert sheet.status_code == 200
    assert "Ada" in sheet.text
    assert "front-left" in sheet.text
    xlsx = client.get(f"/api/rooms/{room_id}/export.xlsx", headers=_auth())
    assert xlsx.status_code == 200
    assert xlsx.content[:2] == b"PK"

    poll = client.post(
        f"/api/rooms/{room_id}/polls",
        headers=_auth(),
        json={"question": "Pick one", "options": ["Yes", "No"], "correct_option": "Yes"},
    ).json()
    hidden = client.get(f"/api/rooms/{room_id}/polls").json()["polls"][0]
    assert "correct_option" not in hidden
    answered = client.post(
        f"/api/rooms/{room_id}/polls/{poll['id']}/answers",
        json={"student_id": "stu-1", "option": "No", "seat_zone": "front-left"},
    )
    assert answered.status_code == 200


def test_llm_config_never_returns_the_key_and_test_classifies_errors():
    application, client = _app()

    def handler(request):
        assert request.headers["authorization"] == f"Bearer {SECRET}"
        return httpx.Response(401, json={"error": {"message": f"invalid {SECRET}"}})

    application.state.http_transport = httpx.MockTransport(handler)
    saved = client.post(
        "/api/llm/config",
        headers=_auth(),
        json={"provider": "openai", "model": "gpt-test", "api_key": SECRET, "base_url": ""},
    )
    assert saved.status_code == 200
    assert SECRET not in saved.text
    assert saved.json()["key_configured"] is True
    assert "api_key" not in saved.json()

    tested = client.post(
        "/api/llm/test",
        headers=_auth(),
        json={"provider": "openai", "model": "gpt-test"},
    )
    body = tested.json()
    assert tested.status_code == 200
    assert body["status"] == "error"
    assert body["category"] == "invalid_key"
    assert SECRET not in tested.text

    unknown = client.post(
        "/api/llm/test",
        headers=_auth(),
        json={"provider": "made-up", "model": "x", "api_key": SECRET},
    )
    assert unknown.json()["category"] == "unknown_provider"
    assert SECRET not in unknown.text


def test_summary_without_a_key_does_not_invent_output():
    _application, client = _app()
    room = client.post("/api/rooms", json={"title": "Lesson"}, headers=_auth()).json()
    refused = client.post(f"/api/rooms/{room['id']}/agent/summary", headers=_auth(), json={})
    assert refused.status_code == 503
    assert refused.json()["error"] == NOT_CONFIGURED
    assert "stub" not in refused.text.lower()


def test_summary_agent_and_name_redaction():
    application, client = _app()
    room = client.post("/api/rooms", json={"title": "Lesson"}, headers=_auth()).json()
    room_id = room["id"]
    client.post(
        f"/api/rooms/{room_id}/comments",
        json={"student_id": "stu-9", "student_name": "Ada Lovelace", "text": "Ada Lovelace is lost on HMAC."},
    )
    client.post(
        f"/api/rooms/{room_id}/transcript",
        headers=_auth(),
        json={"transcript": "00:02 Ada Lovelace asked about HMAC.\n"},
    )
    snapshot, _names, _ids = application.state.store.snapshot(room_id)
    encoded = json.dumps(snapshot)
    assert "Ada Lovelace" not in encoded
    assert "[name]" in snapshot["transcript"]

    class Scripted:
        def complete(self, messages, tools, max_tokens=1200):
            names = [call.name for message in messages if message.tool_calls for call in message.tool_calls]
            if "get_transcript_segment" not in names:
                return LLMResponse(
                    text="",
                    tool_calls=[ToolCall("1", "get_transcript_segment", {"keyword": "HMAC"})],
                    model="script",
                )
            return LLMResponse(
                text="",
                tool_calls=[ToolCall("2", "produce_report", {"report": {
                    "kind": "lesson_summary",
                    "topics": [{"title": "HMAC"}],
                    "zone_findings": [],
                    "recommendations": ["Revisit the definition."],
                    "missing_data": [],
                    "citations": [{"finding": "HMAC was discussed", "source": "transcript"}],
                }})],
                model="script",
            )

    application.state.provider_factory = lambda _config: Scripted()
    application.state.store.llm.provider = "openai"
    application.state.store.llm.model = "gpt-test"
    application.state.store.llm.api_key = SECRET
    report = client.post(f"/api/rooms/{room_id}/agent/summary", headers=_auth(), json={})
    assert report.status_code == 200
    assert report.json()["report"]["kind"] == "lesson_summary"
    assert report.json()["stub"] is False
    assert SECRET not in report.text
    assert "Ada Lovelace" not in report.text
