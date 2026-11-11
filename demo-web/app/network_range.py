"""Hotspot address check used by the server and the local helper.

The network name is not an input. The bind address is the interface the
helper must listen on. The client range is the only set of peer addresses
that may be marked present. Wide private blocks and public ranges are rejected
so a missing or sloppy setting fails closed.
"""

from __future__ import annotations

import ipaddress


class NetworkConfigError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def normalize_ip(value: str):
    text = (value or "").strip()
    if not text:
        raise NetworkConfigError("missing_network")
    if "%" in text:
        text = text.split("%", 1)[0]
    if text.lower().startswith("::ffff:"):
        text = text.split(":", 3)[-1]
    try:
        return ipaddress.ip_address(text)
    except ValueError as exc:
        raise NetworkConfigError("bad_network") from exc


def validate_hotspot(bind_host: str, cidr: str):
    """Return ``(network, bind_address)`` or raise NetworkConfigError."""
    if not (bind_host or "").strip() or not (cidr or "").strip():
        raise NetworkConfigError("missing_network")
    bind = normalize_ip(bind_host)
    if getattr(bind, "is_unspecified", False) or getattr(bind, "is_multicast", False):
        raise NetworkConfigError("bad_network")
    try:
        network = ipaddress.ip_network(cidr.strip(), strict=False)
    except ValueError as exc:
        raise NetworkConfigError("bad_network") from exc
    if bind.version != network.version or bind not in network:
        raise NetworkConfigError("bind_outside_range")
    if bind.version == 4:
        if bind.is_loopback:
            if network.prefixlen != 32:
                raise NetworkConfigError("range_too_wide")
        elif bind.is_private:
            if network.prefixlen < 24 or network.prefixlen > 30:
                raise NetworkConfigError("range_too_wide")
            if not network.network_address.is_private:
                raise NetworkConfigError("public_range")
        else:
            raise NetworkConfigError("public_range")
    else:
        ula = ipaddress.ip_network("fc00::/7")
        link_local = ipaddress.ip_network("fe80::/10")
        if not (bind in ula or bind in link_local):
            raise NetworkConfigError("public_range")
        if not (network.subnet_of(ula) or network.subnet_of(link_local)):
            raise NetworkConfigError("public_range")
        if network.prefixlen < 64 or network.prefixlen > 120:
            raise NetworkConfigError("range_too_wide")
    return network, bind


def address_in_network(value: str, network: ipaddress._BaseNetwork) -> bool:
    try:
        address = normalize_ip(value)
    except NetworkConfigError:
        return False
    return address.version == network.version and address in network


def hotspot_notes(network: ipaddress._BaseNetwork) -> list[str]:
    return [
        "The network name is only the label on the Wi-Fi QR. It is not checked.",
        "A phone counts only when its connection arrives on the verifier address and its socket address is inside this range.",
        "This does not identify the person. A relay from inside the range can still forward a challenge.",
        "Another network that uses this same subnet can confuse the operating system. This range is not every private address.",
        f"Accepted size: {network.num_addresses} addresses ({network}).",
    ]
