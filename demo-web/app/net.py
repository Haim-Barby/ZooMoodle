"""Client IP and optional campus-subnet check.

Forwarded headers are honored only when the socket peer is a trusted proxy.

On Render the socket peer is the platform proxy (a 10.x address), not the
browser, and traffic reaches that proxy through Cloudflare. A typical request
looks like:

  X-Forwarded-For: <client>, <cloudflare>, <render-10.x>
  CF-Connecting-IP / True-Client-IP: <client>

Cloudflare overwrites CF-Connecting-IP and True-Client-IP, so those headers
are trusted from any trusted peer (local cloudflared on loopback, or Render's
proxy). Taking the rightmost hop that is not a private trusted proxy would
return the Cloudflare address, which is not the student and is outside the
campus ranges. X-Forwarded-For is the fallback; private and Cloudflare hops
are skipped so a missing CF header still yields the client.

Uvicorn must not be told to trust every peer: that would copy the leftmost
(browser-controlled) X-Forwarded-For hop into the socket address before this
check runs.
"""

from __future__ import annotations

import ipaddress

DEFAULT_TRUSTED_PROXIES = ("127.0.0.1/32", "::1/128")

# Official Cloudflare ranges: https://www.cloudflare.com/ips-v4/ and /ips-v6/
CLOUDFLARE_RANGES = (
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
    "162.158.0.0/15",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "172.64.0.0/13",
    "131.0.72.0/22",
    "2400:cb00::/32",
    "2606:4700::/32",
    "2803:f800::/32",
    "2405:b500::/32",
    "2405:8100::/32",
    "2a06:98c0::/29",
    "2c0f:f248::/32",
)


def client_ip(
    headers: dict,
    peer: str | None,
    trusted_proxies: tuple[str, ...] = DEFAULT_TRUSTED_PROXIES,
) -> str:
    direct = (peer or "").strip()
    if not peer_is_trusted(direct, trusted_proxies):
        return direct
    # Cloudflare sets these and overwrites a value the browser sent.
    # Trust them from any trusted peer, not only loopback: Render's socket
    # peer is 10.x, not 127.0.0.1.
    for name in ("cf-connecting-ip", "true-client-ip"):
        value = _header(headers, name)
        if value:
            return _hop_host(value.split(",")[0])
    forwarded = _client_from_xff(_header(headers, "x-forwarded-for"), trusted_proxies)
    return forwarded or direct


def _client_from_xff(value: str, trusted_proxies: tuple[str, ...]) -> str:
    hops = [_hop_host(part) for part in value.split(",")]
    hops = [hop for hop in hops if hop]
    for hop in reversed(hops):
        if not _is_forwarding_proxy(hop, trusted_proxies):
            return hop
    return hops[0] if hops else ""


def _is_forwarding_proxy(hop: str, trusted_proxies: tuple[str, ...]) -> bool:
    return peer_is_trusted(hop, trusted_proxies) or peer_is_trusted(hop, CLOUDFLARE_RANGES)


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


def forwarded_debug(headers: dict, peer: str | None) -> str:
    """Compact header summary for campus-check mismatch logs. IPs only."""
    parts = [f"peer={peer or ''}"]
    for name in ("cf-connecting-ip", "true-client-ip", "x-forwarded-for"):
        value = _header(headers, name)
        if value:
            parts.append(f"{name}={value}")
    return " ".join(parts)


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
