"""Guided lecturer launch for macOS and Windows.

A second double-click can start the local verifier from a saved setup.
That is not the same as fully automatic hotspot provisioning. This module
never loads remote code, never changes the firewall, and never claims the
operating system accepted a prompt.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

from helper.hotspot_check import apply_hotspot, capability

MAC_SETTINGS = "x-apple.systempreferences:com.apple.Sharing-Settings.extension"
WINDOWS_SETTINGS = "ms-settings:network-mobilehotspot"


def config_path(home: Path | None = None) -> Path:
    root = Path(home) if home is not None else Path.home()
    return root / ".zoomoodle" / "lecturer-setup.json"


def save_setup(path: Path, setup: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = {
        "server": setup.get("server", ""),
        "room_id": setup.get("room_id", ""),
        "bind_host": setup.get("bind_host", ""),
        "bind_port": int(setup.get("bind_port") or 8787),
        "client_cidr": setup.get("client_cidr", ""),
        "network_name": setup.get("network_name", ""),
        "public_origin": setup.get("public_origin", ""),
        "helper_id": setup.get("helper_id", ""),
        "helper_key": setup.get("helper_key", ""),
        "lecturer_token": setup.get("lecturer_token", ""),
    }
    path.write_text(json.dumps(kept), encoding="utf-8")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def load_setup(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def plan_launch(
    *,
    platform: str,
    opt_in: bool,
    configured: bool,
    hotspot_result: dict | None = None,
    network_ready: bool = False,
) -> dict:
    """Describe what this launch will and will not do. It does not touch the OS."""
    hotspot_result = hotspot_result or {}
    report = {
        "fully_automatic": False,
        "one_click_after_setup": bool(configured),
        "starts_verifier": bool(configured),
        "hotspot_started": False,
        "opened_settings": False,
        "settings_target": "",
        "will_change_firewall": False,
        "downloaded_code": False,
        "silent_admin_prompts": False,
        "manual_remaining": [],
        "same_wifi_adapter": "not_supported" if platform == "darwin" else "adapter_dependent",
    }
    if platform == "darwin":
        report["manual_remaining"].append(
            "macOS Internet Sharing stays manual. This launcher cannot share the same Wi-Fi adapter "
            "you are using for the internet, and it cannot approve the system prompt."
        )
        if opt_in:
            report["opened_settings"] = True
            report["settings_target"] = MAC_SETTINGS
        else:
            report["manual_remaining"].append("Opt in if you want Sharing settings opened. Nothing is opened otherwise.")
    elif platform in ("win32", "cygwin"):
        if opt_in and hotspot_result.get("started") is True:
            report["hotspot_started"] = True
            report["manual_remaining"].append(
                "Windows reported the Mobile Hotspot API started. That still depends on this PC's adapter, "
                "and the system may have shown its own prompt."
            )
        else:
            report["manual_remaining"].append(
                "Turn on Mobile Hotspot in Settings if it is not already on. "
                "The legacy netsh hostednetwork command is not used."
            )
            if opt_in:
                report["opened_settings"] = True
                report["settings_target"] = WINDOWS_SETTINGS
                if hotspot_result.get("reason"):
                    report["manual_remaining"].append("Windows API result: " + str(hotspot_result["reason"]))
    else:
        report["manual_remaining"].append("Create the hotspot yourself on this operating system, then start the verifier.")
    if not configured:
        report["starts_verifier"] = False
        report["manual_remaining"].append(
            "First run still needs the server URL, lecturer token, room, verifier address, and phone address range."
        )
    elif not network_ready:
        report["starts_verifier"] = False
        report["manual_remaining"].append(
            "Enter the verifier address and the phone address range. The verifier will not start without them."
        )
    return report


def diagnostics(platform: str | None = None) -> dict:
    hot = capability(platform)
    return {
        "python": sys.version.split()[0],
        "hotspot": hot,
        "firewall_changes": False,
        "downloads_code": False,
        "fully_automatic": False,
    }


def default_settings_opener(target: str) -> None:
    import subprocess

    if sys.platform == "darwin":
        subprocess.run(["open", target], check=False)
    elif sys.platform == "win32":
        subprocess.run(["cmd", "/c", "start", "", target], check=False)


def main() -> None:
    system = sys.platform
    print("ZooMoodle lecturer launcher")
    print("Fully automatic hotspot setup is not available.")
    print(json.dumps(diagnostics(system)["hotspot"]["note"]))
    path = config_path()
    setup = load_setup(path)
    configured = bool(setup.get("server") and setup.get("helper_key") and setup.get("bind_host") and setup.get("room_id"))
    network_ready = bool(setup.get("bind_host") and setup.get("client_cidr"))
    answer = input("Open the documented hotspot settings now? [y/N] ").strip().lower()
    report = plan_launch(
        platform=system,
        opt_in=answer == "y",
        configured=configured,
        network_ready=network_ready,
    )
    if report["opened_settings"] and report["settings_target"]:
        default_settings_opener(report["settings_target"])
        print("Opened settings. Finish the remaining step there if the hotspot is not already on.")
    for line in report["manual_remaining"]:
        print(line)
    if not configured:
        print("Save a setup with helper.launch_wizard.save_setup after pairing. The Wi-Fi password is not stored.")
        print("Apply attempt:", json.dumps(apply_hotspot(system, opt_in=answer == "y")))
        return
    print("Starting the local verifier only. The hotspot is left as you configured it.")
    os.environ["ZOOMODLE_HELPER_KEY"] = setup["helper_key"]
    from helper.presence_helper import PresenceHelper, serve

    helper = PresenceHelper(
        setup["bind_host"],
        setup["server"],
        setup["room_id"],
        setup["helper_id"],
        setup["helper_key"],
        setup.get("public_origin") or setup["server"],
        client_cidr=setup["client_cidr"],
    )
    server = serve(helper, int(setup.get("bind_port") or 8787))
    print("Verifier listening on http://%s:%s/prove" % (setup["bind_host"], setup.get("bind_port") or 8787))
    print("Wi-Fi QR, if you need one, stays on the lecturer page and is not printed here.")
    server.serve_forever()
