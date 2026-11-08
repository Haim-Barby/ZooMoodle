"""Capability report for a lecturer personal hotspot.

This module never changes network, firewall, or sharing settings. macOS and
Windows do not offer one supported unattended API that works on every laptop,
so automation is refused even when the lecturer opts in.
"""

from __future__ import annotations

import sys


def capability(platform: str | None = None) -> dict:
    system = platform or sys.platform
    if system == "darwin":
        return {
            "os": "macos",
            "automated": False,
            "will_change_settings": False,
            "manual_steps": [
                "Open System Settings, General, Sharing, Internet Sharing.",
                "Share from Ethernet (the upstream) to Wi-Fi. Confirm the prompt yourself.",
                "Note the Wi-Fi name, password, and the laptop address on that network (often 192.168.2.1).",
                "Start the ZooMoodle presence helper bound to that address. Do not bind 0.0.0.0.",
            ],
            "not_used": ["launchctl load InternetSharing", "defaults write com.apple.nat"],
            "note": "There is no supported public API that safely turns Internet Sharing on for every Mac. The helper will not click System Settings or load the sharing daemon.",
        }
    if system in ("win32", "cygwin"):
        return {
            "os": "windows",
            "automated": False,
            "will_change_settings": False,
            "manual_steps": [
                "Open Settings, Network & internet, Mobile hotspot, and turn it on yourself.",
                "Whether that switch exists depends on the Wi-Fi adapter. Wi-Fi Direct and the old hosted network are different.",
                "Note the hotspot name, password, and the adapter address (often 192.168.137.1).",
                "Start the ZooMoodle presence helper bound to that address.",
            ],
            "not_used": ["netsh wlan set hostednetwork", "netsh wlan start hostednetwork"],
            "note": "Mobile Hotspot is a Windows Runtime API and is adapter-dependent. The legacy netsh hostednetwork command is not a guarantee and this helper does not run it.",
        }
    return {
        "os": system,
        "automated": False,
        "will_change_settings": False,
        "manual_steps": [
            "This helper does not configure a hotspot on this operating system.",
            "Create the network yourself, then bind the presence helper to its interface address.",
        ],
        "not_used": ["netsh", "launchctl"],
        "note": "No network settings were read or changed.",
    }


def apply_hotspot(platform: str | None = None, opt_in: bool = False) -> dict:
    """Opt-in does not enable a hotspot. It only records that automation is unavailable."""
    report = capability(platform)
    return {
        "changed": False,
        "opt_in": bool(opt_in),
        "reason": "opt_in_required" if not opt_in else "no_supported_automation",
        "os": report["os"],
        "manual_steps": report["manual_steps"],
    }
