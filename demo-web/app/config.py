"""Process settings. Secrets stay in memory and are never logged."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass

from app.net import DEFAULT_TRUSTED_PROXIES

# Ariel University public egress (RIPE inetnum 192.114.48.0 - 192.114.57.255).
DEFAULT_CAMPUS_RANGES = ("192.114.48.0/21", "192.114.56.0/23")
DEFAULT_KEY_FILE = os.path.join("~", ".zoomoodle", "lecturer-key.txt")


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


def _on_render() -> bool:
    return os.environ.get("RENDER", "").strip().lower() == "true"


def _list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)) or default)
    except ValueError:
        return default


def read_or_create_key_file(path: str) -> tuple[str, bool]:
    """Return ``(key, created)``. A new key file is written with mode 600."""
    full = os.path.expanduser(path)
    if os.path.exists(full):
        with open(full, encoding="utf-8") as handle:
            key = handle.read().strip()
        if key:
            return key, False
    os.makedirs(os.path.dirname(full), mode=0o700, exist_ok=True)
    key = "zmk_" + secrets.token_urlsafe(32)
    fd = os.open(full, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(key + "\n")
    os.chmod(full, 0o600)
    return key, True


def _refuse_render_without_secrets() -> None:
    if not _on_render():
        return
    missing = []
    if not _env("ZOOMODLE_MASTER_SECRET"):
        missing.append("ZOOMODLE_MASTER_SECRET")
    if not (_env("ZOOMODLE_LECTURER_KEY") or _env("ZOOMODLE_LECTURER_TOKEN")):
        missing.append("ZOOMODLE_LECTURER_KEY")
    if missing:
        raise SystemExit(
            "Cannot start on Render: " + " and ".join(missing) + " is empty. "
            "Set it under Environment in the Render Dashboard. Startup never prints it."
        )


@dataclass
class Settings:
    master_secret: bytes
    lecturer_key: str
    ephemeral_master_secret: bool = False
    lecturer_key_file: str = ""
    lecturer_key_created: bool = False
    lecturer_name: str = "טום יניב"
    course_name: str = "מערכות נוירונים"
    course_week: int = 4
    campus_ranges: tuple[str, ...] = DEFAULT_CAMPUS_RANGES
    trusted_proxies: tuple[str, ...] = DEFAULT_TRUSTED_PROXIES
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    demo_email_override: str = ""
    llm_timeout_seconds: float = 20.0
    agent_max_steps: int = 8
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def greeting(self) -> str:
        return f"שלום {self.lecturer_name}, השבוע שבוע {self.course_week} בקורס {self.course_name}"

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @staticmethod
    def from_env() -> "Settings":
        load_dotenv()
        _refuse_render_without_secrets()
        secret_text = _env("ZOOMODLE_MASTER_SECRET")
        ephemeral = not secret_text
        if ephemeral:
            secret_text = secrets.token_hex(32)
        key = _env("ZOOMODLE_LECTURER_KEY") or _env("ZOOMODLE_LECTURER_TOKEN")
        key_file = ""
        created = False
        if not key:
            key_file = os.path.expanduser(_env("ZOOMODLE_LECTURER_KEY_FILE") or DEFAULT_KEY_FILE)
            key, created = read_or_create_key_file(key_file)
        try:
            timeout = float(_env("LLM_TIMEOUT_SECONDS", "20") or "20")
        except ValueError:
            timeout = 20.0
        return Settings(
            master_secret=secret_text.encode("utf-8"),
            lecturer_key=key,
            ephemeral_master_secret=ephemeral,
            lecturer_key_file=key_file,
            lecturer_key_created=created,
            lecturer_name=_env("ZOOMODLE_LECTURER_NAME") or "טום יניב",
            course_name=_env("ZOOMODLE_COURSE_NAME") or "מערכות נוירונים",
            course_week=_int("ZOOMODLE_COURSE_WEEK", 4),
            # An empty value (also the legacy ZOOMODLE_ALLOWED_SUBNETS="") means the default ranges.
            campus_ranges=_list("ZOOMODLE_CAMPUS_RANGES", ()) or _list("ZOOMODLE_ALLOWED_SUBNETS", ()) or DEFAULT_CAMPUS_RANGES,
            trusted_proxies=_list("ZOOMODLE_TRUSTED_PROXIES", DEFAULT_TRUSTED_PROXIES) or DEFAULT_TRUSTED_PROXIES,
            smtp_host=_env("ZOOMODLE_SMTP_HOST"),
            smtp_port=_int("ZOOMODLE_SMTP_PORT", 587),
            smtp_user=_env("ZOOMODLE_SMTP_USER"),
            smtp_password=_env("ZOOMODLE_SMTP_PASSWORD"),
            smtp_from=_env("ZOOMODLE_SMTP_FROM") or _env("ZOOMODLE_SMTP_USER"),
            demo_email_override=_env("DEMO_EMAIL_OVERRIDE"),
            llm_timeout_seconds=timeout,
            agent_max_steps=max(1, _int("ZOOMODLE_AGENT_MAX_STEPS", 8)),
            host=_env("ZOOMODLE_HOST", "0.0.0.0") or "0.0.0.0",
            port=_int("ZOOMODLE_PORT", 8000),
        )
