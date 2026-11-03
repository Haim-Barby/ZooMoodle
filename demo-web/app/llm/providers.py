"""LLM adapters. The API key is used as a header and scrubbed from errors."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.parse import quote

import httpx

KNOWN_PROVIDERS = (
    "openai",
    "anthropic",
    "gemini",
    "xai",
    "ollama",
    "openai_compatible",
)
KEY_OPTIONAL = {"ollama", "openai_compatible"}

DEFAULT_BASE = {
    "openai": "https://api.openai.com/v1",
    "xai": "https://api.x.ai/v1",
    "ollama": "http://127.0.0.1:11434/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
}


class ProviderFailure(Exception):
    def __init__(self, category: str, message: str, status_code: int | None = None):
        super().__init__(message)
        self.category = category
        self.message = message
        self.status_code = status_code


def scrub(text: str, secret: str) -> str:
    if not text:
        return ""
    cleaned = text
    if secret:
        cleaned = cleaned.replace(secret, "[redacted]")
    return cleaned[:500]


def classify_status(status: int) -> str:
    if status == 401:
        return "invalid_key"
    if status in (403, 404):
        return "no_access"
    if status == 429:
        return "rate_limit"
    return "upstream"


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatMessage:
    role: str
    content: str = ""
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall]
    model: str


@dataclass
class ConnectResult:
    status: str
    provider: str
    model: str
    latency_ms: int | None
    tool_calling: str
    category: str | None
    message: str

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "provider": self.provider,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "tool_calling": self.tool_calling,
            "category": self.category,
            "message": self.message,
        }


@dataclass
class LLMConfig:
    provider: str = ""
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    timeout_seconds: float = 8.0

    def key_configured(self) -> bool:
        provider = self.provider.strip().lower()
        if provider in KEY_OPTIONAL:
            return bool(self.model.strip())
        return bool(self.api_key)


PING_TOOL = ToolSpec(
    name="ping",
    description="Confirm that this model can call a tool.",
    parameters={
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
    },
)


def _error_text(response: httpx.Response, secret: str) -> str:
    try:
        payload = response.json()
    except Exception:
        return scrub(f"HTTP {response.status_code}", secret)
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            return scrub(str(error["message"]), secret)
        if isinstance(error, str):
            return scrub(error, secret)
        if payload.get("message"):
            return scrub(str(payload["message"]), secret)
    return scrub(f"HTTP {response.status_code}", secret)


def _parse_arguments(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class LLMClient:
    """Thin facade over one provider adapter."""

    def __init__(self, provider: "BaseProvider"):
        self.provider = provider

    def complete(self, messages: list[ChatMessage], tools: list[ToolSpec], max_tokens: int = 1200) -> LLMResponse:
        return self.provider.complete(messages, tools, max_tokens=max_tokens)

    def test_connection(self) -> ConnectResult:
        return self.provider.test_connection()


class BaseProvider:
    def __init__(self, config: LLMConfig, transport: httpx.BaseTransport | None = None):
        self.config = config
        self.transport = transport

    def complete(self, messages: list[ChatMessage], tools: list[ToolSpec] | None, max_tokens: int) -> LLMResponse:
        raise NotImplementedError

    def test_connection(self) -> ConnectResult:
        started = time.perf_counter()
        provider = self.config.provider.strip().lower()
        model = self.config.model.strip()

        def elapsed() -> int:
            return int((time.perf_counter() - started) * 1000)

        def failure(exc: ProviderFailure) -> ConnectResult:
            return ConnectResult(
                status="error",
                provider=provider,
                model=model,
                latency_ms=elapsed(),
                tool_calling="not_checked",
                category=exc.category,
                message=exc.message,
            )

        try:
            response = self.complete(
                [ChatMessage("user", "Call the ping tool with ok=true.")],
                [PING_TOOL],
                max_tokens=64,
            )
            tool = "supported" if response.tool_calls else "not_supported"
            return ConnectResult(
                status="ok",
                provider=provider,
                model=response.model or model,
                latency_ms=elapsed(),
                tool_calling=tool,
                category=None,
                message="Connection succeeded.",
            )
        except ProviderFailure as exc:
            if exc.status_code != 400:
                return failure(exc)
            try:
                response = self.complete(
                    [ChatMessage("user", "Reply with the single word pong.")],
                    None,
                    max_tokens=16,
                )
            except ProviderFailure as retry:
                return failure(retry)
            return ConnectResult(
                status="ok",
                provider=provider,
                model=response.model or model,
                latency_ms=elapsed(),
                tool_calling="not_supported",
                category=None,
                message="Connection succeeded. The tool-calling request was rejected, so tool calling is marked not supported.",
            )
        except httpx.TimeoutException:
            return ConnectResult(
                status="error",
                provider=provider,
                model=model,
                latency_ms=elapsed(),
                tool_calling="not_checked",
                category="timeout",
                message="The provider did not answer before the timeout.",
            )
        except httpx.TransportError as exc:
            return ConnectResult(
                status="error",
                provider=provider,
                model=model,
                latency_ms=elapsed(),
                tool_calling="not_checked",
                category="network",
                message=scrub(f"Network error: {exc.__class__.__name__}", self.config.api_key),
            )

    def _client(self) -> httpx.Client:
        timeout = httpx.Timeout(self.config.timeout_seconds)
        kwargs = {"timeout": timeout}
        if self.transport is not None:
            kwargs["transport"] = self.transport
        return httpx.Client(**kwargs)

    def _post(self, url: str, headers: dict, body: dict) -> httpx.Response:
        secret = self.config.api_key
        try:
            with self._client() as client:
                response = client.post(url, headers=headers, json=body)
        except httpx.TimeoutException:
            raise
        except httpx.TransportError:
            raise
        if response.status_code >= 400:
            raise ProviderFailure(
                classify_status(response.status_code),
                _error_text(response, secret),
                response.status_code,
            )
        return response


class OpenAICompatibleProvider(BaseProvider):
    """OpenAI, xAI, Ollama, and any other /chat/completions server."""

    def complete(self, messages, tools, max_tokens: int = 1200) -> LLMResponse:
        self._ready()
        url = self._base() + "/chat/completions"
        headers = {"content-type": "application/json"}
        if self.config.api_key:
            headers["authorization"] = f"Bearer {self.config.api_key}"
        body: dict = {
            "model": self.config.model.strip(),
            "messages": _openai_messages(messages),
            "max_tokens": max_tokens,
            "temperature": 0,
        }
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ]
        response = self._post(url, headers, body)
        try:
            payload = response.json()
            message = payload["choices"][0]["message"]
        except Exception as exc:
            raise ProviderFailure("upstream", "The provider returned a response without choices.", response.status_code) from exc
        calls = []
        for index, raw in enumerate(message.get("tool_calls") or []):
            function = raw.get("function") or {}
            calls.append(
                ToolCall(
                    id=str(raw.get("id") or f"call_{index}"),
                    name=str(function.get("name") or ""),
                    arguments=_parse_arguments(function.get("arguments")),
                )
            )
        text = message.get("content") or ""
        return LLMResponse(text=text, tool_calls=calls, model=str(payload.get("model") or self.config.model))

    def _ready(self) -> None:
        provider = self.config.provider.strip().lower()
        if provider not in ("openai", "xai", "ollama", "openai_compatible"):
            raise ProviderFailure("unknown_provider", f"Unknown provider '{provider}'.")
        if not self.config.model.strip():
            raise ProviderFailure("invalid_request", "Set a model name before calling the provider.")
        if provider == "openai_compatible" and not (self.config.base_url or "").strip():
            raise ProviderFailure("invalid_request", "Set a base URL for the OpenAI-compatible endpoint.")
        if provider not in KEY_OPTIONAL and not self.config.api_key:
            raise ProviderFailure("invalid_key", "No API key is configured for this provider.")

    def _base(self) -> str:
        provider = self.config.provider.strip().lower()
        base = (self.config.base_url or DEFAULT_BASE.get(provider, "")).strip().rstrip("/")
        if not base:
            raise ProviderFailure("invalid_request", "Set a base URL for this provider.")
        return base


class AnthropicProvider(BaseProvider):
    def complete(self, messages, tools, max_tokens: int = 1200) -> LLMResponse:
        if self.config.provider.strip().lower() != "anthropic":
            raise ProviderFailure("unknown_provider", "Unknown provider.")
        if not self.config.model.strip():
            raise ProviderFailure("invalid_request", "Set a model name before calling the provider.")
        if not self.config.api_key:
            raise ProviderFailure("invalid_key", "No API key is configured for this provider.")
        system, converted = _anthropic_messages(messages)
        url = (self.config.base_url or DEFAULT_BASE["anthropic"]).rstrip("/") + "/v1/messages"
        headers = {
            "content-type": "application/json",
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
        }
        body: dict = {
            "model": self.config.model.strip(),
            "max_tokens": max_tokens,
            "messages": converted,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [
                {"name": tool.name, "description": tool.description, "input_schema": tool.parameters}
                for tool in tools
            ]
        response = self._post(url, headers, body)
        try:
            payload = response.json()
            blocks = payload.get("content") or []
        except Exception as exc:
            raise ProviderFailure("upstream", "The provider returned an unreadable response.", response.status_code) from exc
        text = []
        calls = []
        for index, block in enumerate(blocks):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text.append(block.get("text") or "")
            elif block.get("type") == "tool_use":
                calls.append(
                    ToolCall(
                        id=str(block.get("id") or f"tool_{index}"),
                        name=str(block.get("name") or ""),
                        arguments=_parse_arguments(block.get("input")),
                    )
                )
        return LLMResponse(text="\n".join(text).strip(), tool_calls=calls, model=str(payload.get("model") or self.config.model))


class GeminiProvider(BaseProvider):
    def complete(self, messages, tools, max_tokens: int = 1200) -> LLMResponse:
        if self.config.provider.strip().lower() != "gemini":
            raise ProviderFailure("unknown_provider", "Unknown provider.")
        if not self.config.model.strip():
            raise ProviderFailure("invalid_request", "Set a model name before calling the provider.")
        if not self.config.api_key:
            raise ProviderFailure("invalid_key", "No API key is configured for this provider.")
        system, contents = _gemini_messages(messages)
        model = quote(self.config.model.strip(), safe="")
        base = (self.config.base_url or DEFAULT_BASE["gemini"]).rstrip("/")
        url = f"{base}/models/{model}:generateContent"
        headers = {"content-type": "application/json", "x-goog-api-key": self.config.api_key}
        body: dict = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = [
                {
                    "functionDeclarations": [
                        {"name": tool.name, "description": tool.description, "parameters": tool.parameters}
                        for tool in tools
                    ]
                }
            ]
        response = self._post(url, headers, body)
        try:
            payload = response.json()
            parts = payload["candidates"][0]["content"].get("parts") or []
        except Exception as exc:
            raise ProviderFailure("upstream", "The provider returned a response without candidates.", response.status_code) from exc
        text = []
        calls = []
        for index, part in enumerate(parts):
            if not isinstance(part, dict):
                continue
            if "text" in part:
                text.append(part.get("text") or "")
            call = part.get("functionCall")
            if isinstance(call, dict):
                calls.append(
                    ToolCall(
                        id=f"gem_{index}",
                        name=str(call.get("name") or ""),
                        arguments=_parse_arguments(call.get("args")),
                    )
                )
        reported = str(payload.get("modelVersion") or self.config.model)
        return LLMResponse(text="\n".join(text).strip(), tool_calls=calls, model=reported)


def build_provider(config: LLMConfig, transport: httpx.BaseTransport | None = None) -> BaseProvider:
    name = config.provider.strip().lower()
    if name in ("openai", "xai", "ollama", "openai_compatible"):
        return OpenAICompatibleProvider(config, transport)
    if name == "anthropic":
        return AnthropicProvider(config, transport)
    if name == "gemini":
        return GeminiProvider(config, transport)
    raise ProviderFailure("unknown_provider", f"Unknown provider '{config.provider}'. Choose one of: {', '.join(KNOWN_PROVIDERS)}.")


def _openai_messages(messages: list[ChatMessage]) -> list[dict]:
    out = []
    for message in messages:
        if message.role == "tool":
            out.append({"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content})
        elif message.role == "assistant" and message.tool_calls:
            out.append(
                {
                    "role": "assistant",
                    "content": message.content or None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                        }
                        for call in message.tool_calls
                    ],
                }
            )
        else:
            out.append({"role": message.role, "content": message.content})
    return out


def _anthropic_messages(messages: list[ChatMessage]) -> tuple[str, list[dict]]:
    system = []
    out: list[dict] = []
    pending: list[dict] = []

    def flush() -> None:
        nonlocal pending
        if pending:
            out.append({"role": "user", "content": pending})
            pending = []

    for message in messages:
        if message.role == "system":
            system.append(message.content)
            continue
        if message.role == "tool":
            pending.append({"type": "tool_result", "tool_use_id": message.tool_call_id, "content": message.content})
            continue
        flush()
        if message.role == "user":
            out.append({"role": "user", "content": message.content})
        elif message.role == "assistant":
            blocks = []
            if message.content:
                blocks.append({"type": "text", "text": message.content})
            for call in message.tool_calls or []:
                blocks.append({"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments})
            out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})
    flush()
    return "\n".join(system).strip(), out


def _gemini_messages(messages: list[ChatMessage]) -> tuple[str, list[dict]]:
    system = []
    contents: list[dict] = []
    for message in messages:
        if message.role == "system":
            system.append(message.content)
            continue
        if message.role == "tool":
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": message.name or "tool",
                                "response": {"content": message.content},
                            }
                        }
                    ],
                }
            )
            continue
        if message.role == "assistant":
            parts = []
            if message.content:
                parts.append({"text": message.content})
            for call in message.tool_calls or []:
                parts.append({"functionCall": {"name": call.name, "args": call.arguments}})
            contents.append({"role": "model", "parts": parts or [{"text": ""}]})
        else:
            contents.append({"role": "user", "parts": [{"text": message.content}]})
    return "\n".join(system).strip(), contents

