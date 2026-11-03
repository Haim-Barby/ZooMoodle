"""Process settings. API keys stay in memory and are never logged."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass

from app.net import DEFAULT_TRUSTED_PROXIES


def load_dotenv(path: str = ".env") -> None:
    """Load KEY=VALUE lines. Existing environment variables win."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _refuse_render_without_secrets() -> None:
    """Render must get both secrets from the dashboard, not from a log line."""
    if os.environ.get("RENDER", "").strip().lower() != "true":
        return
    missing = [
        name
        for name in ("ZOOMODLE_MASTER_SECRET", "ZOOMODLE_LECTURER_TOKEN")
        if not os.environ.get(name, "").strip()
    ]
    if not missing:
        return
    listed = " and ".join(missing)
    raise SystemExit(
        f"Cannot start on Render: {listed} is empty. "
        "In the Render Dashboard open this service, then Environment, and set a value. "
        "Reveal ZOOMODLE_LECTURER_TOKEN there. Startup does not print that token."
    )


@dataclass
class Settings:
    master_secret: bytes
    lecturer_token: str
    ephemeral_master_secret: bool = False
    generated_lecturer_token: bool = False
    token_window_seconds: int = 5
    grace_windows: int = 1
    challenge_max_age_seconds: float = 8.0
    allowed_subnets: tuple[str, ...] = ()
    trusted_proxies: tuple[str, ...] = DEFAULT_TRUSTED_PROXIES
    llm_provider: str = ""
    llm_model: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_timeout_seconds: float = 8.0
    agent_max_steps: int = 8
    host: str = "0.0.0.0"
    port: int = 8000

    @staticmethod
    def from_env() -> "Settings":
        load_dotenv()
        _refuse_render_without_secrets()
        secret_text = _env("ZOOMODLE_MASTER_SECRET")
        ephemeral = not secret_text
        if ephemeral:
            secret_text = secrets.token_hex(32)
        token = _env("ZOOMODLE_LECTURER_TOKEN")
        generated_token = not token
        if generated_token:
            token = secrets.token_urlsafe(18)
        subnets = tuple(
            part.strip() for part in _env("ZOOMODLE_ALLOWED_SUBNETS").split(",") if part.strip()
        )
        proxy_text = os.environ.get("ZOOMODLE_TRUSTED_PROXIES")
        if proxy_text is None or not proxy_text.strip():
            proxies = DEFAULT_TRUSTED_PROXIES
        else:
            proxies = tuple(part.strip() for part in proxy_text.split(",") if part.strip())
        try:
            window = int(_env("ZOOMODLE_TOKEN_WINDOW_SECONDS", "5") or "5")
        except ValueError:
            window = 5
        try:
            steps = int(_env("ZOOMODLE_AGENT_MAX_STEPS", "8") or "8")
        except ValueError:
            steps = 8
        try:
            timeout = float(_env("LLM_TIMEOUT_SECONDS", "8") or "8")
        except ValueError:
            timeout = 8.0
        try:
            port = int(_env("ZOOMODLE_PORT", "8000") or "8000")
        except ValueError:
            port = 8000
        return Settings(
            master_secret=secret_text.encode("utf-8"),
            lecturer_token=token,
            ephemeral_master_secret=ephemeral,
            generated_lecturer_token=generated_token,
            token_window_seconds=max(1, window),
            allowed_subnets=subnets,
            trusted_proxies=proxies,
            llm_provider=_env("LLM_PROVIDER"),
            llm_model=_env("LLM_MODEL"),
            llm_base_url=_env("LLM_BASE_URL"),
            llm_api_key=_env("LLM_API_KEY"),
            llm_timeout_seconds=timeout,
            agent_max_steps=max(1, steps),
            host=_env("ZOOMODLE_HOST", "0.0.0.0") or "0.0.0.0",
            port=port,
        )
