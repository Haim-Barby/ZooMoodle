import os
import stat

import pytest

from app.config import Settings, read_or_create_key_file
from tests.conftest import LECTURER_KEY, login, make_client

GREETING = "שלום טום יניב, השבוע שבוע 4 בקורס מערכות נוירונים"


def test_lecturer_key_sign_in_shows_the_greeting():
    _app, client = make_client()
    response = client.post("/api/lecturer/login", json={"key": LECTURER_KEY})
    assert response.status_code == 200
    body = response.json()
    assert body["greeting"] == GREETING
    assert LECTURER_KEY not in response.text
    me = client.get("/api/lecturer/me", headers={"x-lecturer-session": body["token"]})
    assert me.json()["greeting"] == GREETING


def test_wrong_key_is_rejected_and_rate_limited():
    _app, client = make_client()
    for _ in range(10):
        assert client.post("/api/lecturer/login", json={"key": "zmk_wrong-wrong-wrong-wrong"}).status_code == 401
    assert client.post("/api/lecturer/login", json={"key": LECTURER_KEY}).status_code == 429


def test_lecturer_routes_need_a_session_not_the_raw_key():
    _app, client = make_client()
    assert client.post("/api/rooms", json={}).status_code == 401
    assert client.post("/api/rooms", json={}, headers={"x-lecturer-session": LECTURER_KEY}).status_code == 401
    headers = login(client)
    room = client.post("/api/rooms", json={}, headers=headers)
    assert room.status_code == 200
    assert room.json()["title"] == "מערכות נוירונים – שבוע 4"
    assert room.json()["student_url"].endswith("/student?room=" + room.json()["id"])
    client.post("/api/lecturer/logout", headers=headers)
    assert client.get("/api/rooms", headers=headers).status_code == 401


def test_key_file_is_created_private_and_reused(tmp_path):
    path = str(tmp_path / ".zoomoodle" / "lecturer-key.txt")
    key, created = read_or_create_key_file(path)
    assert created and key.startswith("zmk_") and len(key) > 40
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    again, created_again = read_or_create_key_file(path)
    assert again == key and not created_again


def test_render_refuses_to_start_without_secrets(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("ZOOMODLE_MASTER_SECRET", raising=False)
    monkeypatch.delenv("ZOOMODLE_LECTURER_KEY", raising=False)
    monkeypatch.delenv("ZOOMODLE_LECTURER_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        Settings.from_env()


def test_env_key_and_default_campus_ranges(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("ZOOMODLE_CAMPUS_RANGES", raising=False)
    monkeypatch.delenv("ZOOMODLE_ALLOWED_SUBNETS", raising=False)
    monkeypatch.setenv("ZOOMODLE_LECTURER_KEY", "zmk_from-env-0123456789abcdef")
    settings = Settings.from_env()
    assert settings.lecturer_key == "zmk_from-env-0123456789abcdef"
    assert settings.campus_ranges == ("192.114.48.0/21", "192.114.56.0/23")
    assert settings.lecturer_key_file == ""


def test_empty_legacy_subnet_setting_still_uses_campus_ranges(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("ZOOMODLE_ALLOWED_SUBNETS", "")
    monkeypatch.setenv("ZOOMODLE_CAMPUS_RANGES", "")
    monkeypatch.setenv("ZOOMODLE_LECTURER_KEY", "zmk_from-env-0123456789abcdef")
    assert Settings.from_env().campus_ranges == ("192.114.48.0/21", "192.114.56.0/23")


def test_startup_message_names_the_key_file_but_not_the_key(capsys, tmp_path):
    from app import main as main_module

    path = str(tmp_path / "k.txt")
    key, _ = read_or_create_key_file(path)
    settings = Settings(master_secret=b"m" * 32, lecturer_key=key, lecturer_key_file=path, lecturer_key_created=True)
    main_module._announce.__dict__.pop("done", None)
    import sys
    saved = sys.modules.pop("pytest")
    try:
        main_module._announce(settings)
    finally:
        sys.modules["pytest"] = saved
        main_module._announce.done = True
    out = capsys.readouterr().out
    assert path in out and key not in out
