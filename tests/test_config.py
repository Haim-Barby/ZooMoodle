import pytest

from app.config import Settings


def test_render_refuses_to_start_when_secrets_are_missing(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("ZOOMODLE_MASTER_SECRET", raising=False)
    monkeypatch.delenv("ZOOMODLE_LECTURER_TOKEN", raising=False)
    with pytest.raises(SystemExit) as caught:
        Settings.from_env()
    message = str(caught.value)
    assert "ZOOMODLE_MASTER_SECRET" in message
    assert "ZOOMODLE_LECTURER_TOKEN" in message
    assert "Render Dashboard" in message
    assert "does not print" in message


def test_render_starts_when_the_dashboard_set_both_secrets(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("ZOOMODLE_MASTER_SECRET", "render-master-secret")
    monkeypatch.setenv("ZOOMODLE_LECTURER_TOKEN", "render-lecturer-token")
    settings = Settings.from_env()
    assert settings.ephemeral_master_secret is False
    assert settings.generated_lecturer_token is False
    assert settings.lecturer_token == "render-lecturer-token"
    assert settings.master_secret == b"render-master-secret"


def test_local_startup_still_generates_a_missing_secret(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("ZOOMODLE_MASTER_SECRET", raising=False)
    monkeypatch.delenv("ZOOMODLE_LECTURER_TOKEN", raising=False)
    settings = Settings.from_env()
    assert settings.ephemeral_master_secret is True
    assert settings.generated_lecturer_token is True
    assert settings.lecturer_token
