"""The lecturer launcher reports manual hotspot steps instead of pretending."""

import json
import stat
from pathlib import Path

from helper.launch_wizard import config_path, load_setup, plan_launch, save_setup

ROOT = Path(__file__).resolve().parents[1]


def test_macos_never_claims_the_hotspot_started():
    report = plan_launch(platform="darwin", opt_in=True, configured=True)
    assert report["fully_automatic"] is False
    assert report["hotspot_started"] is False
    assert report["same_wifi_adapter"] == "not_supported"
    assert report["silent_admin_prompts"] is False
    assert report["will_change_firewall"] is False
    assert report["one_click_after_setup"] is True
    assert report["starts_verifier"] is True
    assert "Internet Sharing" in " ".join(report["manual_remaining"])
    assert report["settings_target"].startswith("x-apple.systempreferences:")


def test_windows_opt_in_without_an_api_success_stays_manual():
    report = plan_launch(
        platform="win32",
        opt_in=True,
        configured=True,
        hotspot_result={"started": False, "reason": "adapter_DisabledByOperator"},
    )
    assert report["hotspot_started"] is False
    assert report["fully_automatic"] is False
    assert "netsh" in " ".join(report["manual_remaining"])
    assert report["settings_target"] == "ms-settings:network-mobilehotspot"
    started = plan_launch(
        platform="win32",
        opt_in=True,
        configured=True,
        hotspot_result={"started": True, "reason": "api_reported_started"},
    )
    assert started["hotspot_started"] is True
    assert started["fully_automatic"] is False
    assert "adapter" in " ".join(started["manual_remaining"])


def test_first_run_does_not_start_the_verifier_and_setup_omits_the_wifi_password(tmp_path):
    report = plan_launch(platform="darwin", opt_in=False, configured=False)
    assert report["starts_verifier"] is False
    assert report["opened_settings"] is False
    path = config_path(tmp_path)
    save_setup(
        path,
        {
            "server": "https://class.example",
            "room_id": "abc",
            "bind_host": "192.168.2.1",
            "helper_id": "hid",
            "helper_key": "secret-key",
            "lecturer_token": "lecturer-secret",
            "wifi_password": "should-not-stick",
        },
    )
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600
    saved = load_setup(path)
    assert saved["bind_host"] == "192.168.2.1"
    assert "wifi_password" not in saved
    assert "should-not-stick" not in path.read_text(encoding="utf-8")
    text = json.dumps(report)
    assert "secret-key" not in text
    assert "lecturer-secret" not in text


def test_launcher_files_do_not_fetch_or_force_a_hotspot():
    mac = (ROOT / "launch" / "macos" / "ZooMoodle Lecturer.command").read_text(encoding="utf-8")
    windows = (ROOT / "launch" / "windows" / "ZooMoodle Lecturer.bat").read_text(encoding="utf-8")
    script = (ROOT / "helper" / "windows_hotspot.ps1").read_text(encoding="utf-8")
    assert "curl" not in mac.lower()
    assert "launchctl" not in mac
    assert "sudo" not in mac
    assert "netsh" not in windows.lower()
    assert "Invoke-Expression" not in script
    assert "DownloadString" not in script
    assert "netsh" not in script.lower()
    assert "StartTetheringAsync" in script
    assert "OptIn" in script
