"""Client IP and optional campus-subnet check.

Forwarded headers are honored only when the socket peer is a trusted proxy.
cloudflared on the lecturer laptop connects from loopback, which is the default.
Render's proxy is not loopback. The blueprint sets FORWARDED_ALLOW_IPS so
uvicorn stores the first X-Forwarded-For hop as this peer, and it widens
ZOOMODLE_TRUSTED_PROXIES to private proxy ranges. This default stays loopback,
so a direct client cannot spoof a campus address.
"""

from __future__ import annotations

import ipaddress

DEFAULT_TRUSTED_PROXIES = ("127.0.0.1/32", "::1/128")


def client_ip(
    headers: dict,
    peer: str | None,
    trusted_proxies: tuple[str, ...] = DEFAULT_TRUSTED_PROXIES,
) -> str:
    direct = (peer or "").strip()
    if peer_is_trusted(direct, trusted_proxies):
        forwarded = _header(headers, "cf-connecting-ip") or _header(headers, "x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return direct


def peer_is_trusted(peer: str, trusted_proxies: tuple[str, ...]) -> bool:
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    for raw in trusted_proxies:
        try:
            network = ipaddress.ip_network(raw, strict=False)
        except ValueError:
            continue
        if address in network:
            return True
    return False


def _header(headers: dict, name: str) -> str:
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() == wanted and value and str(value).strip():
            return str(value).strip()
    return ""


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
