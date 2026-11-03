import json

import httpx

from app.llm.providers import (
    LLMClient,
    LLMConfig,
    ProviderFailure,
    build_provider,
)


SECRET = "sk-test-secret"


def _config(provider="openai", **overrides):
    values = dict(provider=provider, model="gpt-test", base_url="", api_key=SECRET, timeout_seconds=2)
    values.update(overrides)
    return LLMConfig(**values)


def _client(handler, provider="openai", **overrides):
    transport = httpx.MockTransport(handler)
    return LLMClient(build_provider(_config(provider, **overrides), transport))


def _ok_body(tool_calls):
    return {
        "model": "gpt-test",
        "choices": [{"message": {"role": "assistant", "content": "pong", "tool_calls": tool_calls}}],
    }


def test_ok_with_tool_call():
    def handler(_request):
        return httpx.Response(200, json=_ok_body([
            {"id": "call_1", "type": "function", "function": {"name": "ping", "arguments": "{\"ok\": true}"}}
        ]))

    result = _client(handler).test_connection()
    assert result.status == "ok"
    assert result.tool_calling == "supported"
    assert result.model == "gpt-test"
    assert result.latency_ms is not None and result.latency_ms >= 0
    assert SECRET not in result.message


def test_ok_without_tool_call():
    def handler(_request):
        return httpx.Response(200, json=_ok_body([]))

    result = _client(handler).test_connection()
    assert result.status == "ok"
    assert result.tool_calling == "not_supported"


def test_tool_rejection_retries_without_tools():
    def handler(request):
        body = json.loads(request.content.decode())
        if "tools" in body:
            return httpx.Response(400, json={"error": {"message": f"tools refused {SECRET}"}})
        return httpx.Response(200, json=_ok_body([]))

    result = _client(handler).test_connection()
    assert result.status == "ok"
    assert result.tool_calling == "not_supported"
    assert SECRET not in result.message


HTTP_CASES = (
    (401, "invalid_key"),
    (403, "no_access"),
    (404, "no_access"),
    (429, "rate_limit"),
)


def test_http_error_categories():
    for status, category in HTTP_CASES:
        def handler(_request, status=status):
            return httpx.Response(status, json={"error": {"message": f"nope {SECRET}"}})

        result = _client(handler).test_connection()
        assert result.status == "error"
        assert result.category == category
        assert SECRET not in result.message
        assert result.tool_calling == "not_checked"


def test_timeout_and_network():
    def timeout(_request):
        raise httpx.ReadTimeout("slow")

    result = _client(timeout).test_connection()
    assert result.category == "timeout"
    assert SECRET not in json.dumps(result.as_dict())

    def down(_request):
        raise httpx.ConnectError("refused")

    result = _client(down).test_connection()
    assert result.category == "network"
    assert SECRET not in result.message


def test_unknown_provider_and_missing_key_make_no_claim_of_success():
    try:
        build_provider(LLMConfig(provider="made-up", model="x", api_key=SECRET))
        raise AssertionError("unknown provider should fail")
    except ProviderFailure as exc:
        assert exc.category == "unknown_provider"

    result = _client(lambda _request: httpx.Response(200, json=_ok_body([])), api_key="").test_connection()
    assert result.status == "error"
    assert result.category == "invalid_key"


def test_anthropic_and_gemini_parse_tool_calls():
    def anthropic(request):
        assert request.headers["x-api-key"] == SECRET
        assert "authorization" not in {key.lower() for key in request.headers}
        return httpx.Response(200, json={
            "model": "claude-test",
            "content": [{"type": "tool_use", "id": "toolu_1", "name": "ping", "input": {"ok": True}}],
        })

    result = _client(anthropic, provider="anthropic").test_connection()
    assert result.status == "ok" and result.tool_calling == "supported"
    assert result.model == "claude-test"

    def gemini(request):
        assert request.headers["x-goog-api-key"] == SECRET
        assert SECRET not in str(request.url)
        return httpx.Response(200, json={
            "modelVersion": "gemini-test",
            "candidates": [{"content": {"parts": [{"functionCall": {"name": "ping", "args": {"ok": True}}}]}}],
        })

    result = _client(gemini, provider="gemini").test_connection()
    assert result.status == "ok" and result.tool_calling == "supported"
    assert result.model == "gemini-test"
