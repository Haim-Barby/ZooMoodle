"""Client IP and optional campus-subnet check.

Forwarded headers are honored only when the socket peer is a trusted proxy.
cloudflared on the lecturer laptop connects from loopback, which is the default,
and only that path trusts CF-Connecting-IP.

On Render the socket peer is the platform proxy, not the browser. The proxy
appends the real client address at the end of X-Forwarded-For, so a value the
browser sent first is ignored. Uvicorn must not be told to trust every peer:
that would copy the leftmost hop into the socket address before this check runs.
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
    if not peer_is_trusted(direct, trusted_proxies):
        return direct
    # cloudflared terminates on loopback and sets CF-Connecting-IP itself.
    # A browser can set that header, so it is ignored from every other peer.
    if peer_is_trusted(direct, DEFAULT_TRUSTED_PROXIES):
        cloudflare = _header(headers, "cf-connecting-ip")
        if cloudflare:
            return _hop_host(cloudflare.split(",")[0])
    forwarded = _client_from_xff(_header(headers, "x-forwarded-for"), trusted_proxies)
    return forwarded or direct


def _client_from_xff(value: str, trusted_proxies: tuple[str, ...]) -> str:
    hops = [_hop_host(part) for part in value.split(",")]
    hops = [hop for hop in hops if hop]
    for hop in reversed(hops):
        if not peer_is_trusted(hop, trusted_proxies):
            return hop
    return hops[0] if hops else ""


def _hop_host(value: str) -> str:
    text = value.strip().strip('"')
    if text.startswith("[") and "]" in text:
        return text[1:text.index("]")]
    if text.count(":") == 1:
        host, port = text.rsplit(":", 1)
        if port.isdigit():
            return host
    return text


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
