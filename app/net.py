"""Client IP and optional campus-subnet check."""

from __future__ import annotations

import ipaddress


def client_ip(headers: dict, fallback: str | None) -> str:
    for name in ("cf-connecting-ip", "x-forwarded-for"):
        value = headers.get(name) or headers.get(name.title())
        if value:
            return value.split(",")[0].strip()
    return fallback or ""


def subnet_status(ip: str, allowed: tuple[str, ...]) -> str:
    if not allowed:
        return "not_configured"
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return "mismatch"
    for raw in allowed:
        try:
            network = ipaddress.ip_network(raw, strict=False)
        except ValueError:
            continue
        if address in network:
            return "match"
    return "mismatch"
