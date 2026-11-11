from app.net import CLOUDFLARE_RANGES, DEFAULT_TRUSTED_PROXIES, client_ip, subnet_status

ARIEL = ("192.114.48.0/21", "192.114.56.0/23")
RENDER_PROXIES = DEFAULT_TRUSTED_PROXIES + ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")


def test_forwarded_header_is_trusted_from_loopback():
    headers = {
        "CF-Connecting-IP": "192.114.52.1",
        "X-Forwarded-For": "198.51.100.9, 127.0.0.1",
    }
    assert client_ip(headers, "127.0.0.1", DEFAULT_TRUSTED_PROXIES) == "192.114.52.1"
    assert client_ip(headers, "::1", DEFAULT_TRUSTED_PROXIES) == "192.114.52.1"
    # The rightmost untrusted hop is the client. 127.0.0.1 is the proxy and is skipped.
    appended = {"X-Forwarded-For": "203.0.113.4, 192.114.52.1"}
    assert client_ip(appended, "127.0.0.1", DEFAULT_TRUSTED_PROXIES) == "192.114.52.1"
    via_proxy = {"X-Forwarded-For": "192.114.52.1, 127.0.0.1"}
    assert client_ip(via_proxy, "127.0.0.1", DEFAULT_TRUSTED_PROXIES) == "192.114.52.1"


def test_render_uses_cloudflare_client_headers_from_a_private_peer():
    """Render's socket peer is 10.x. The real student IP is in CF-Connecting-IP."""
    headers = {
        "CF-Connecting-IP": "192.114.52.1",
        "True-Client-IP": "192.114.52.1",
        "X-Forwarded-For": "192.114.52.1, 172.71.195.123, 10.226.90.65",
    }
    assert client_ip(headers, "10.193.180.8", RENDER_PROXIES) == "192.114.52.1"
    # CF-Connecting-IP wins over a spoofed leftmost X-Forwarded-For hop.
    spoofed = {
        "CF-Connecting-IP": "192.114.52.1",
        "X-Forwarded-For": "203.0.113.10, 192.114.52.1, 172.71.195.123, 10.226.90.65",
    }
    assert client_ip(spoofed, "10.193.180.8", RENDER_PROXIES) == "192.114.52.1"
    # True-Client-IP is used when CF-Connecting-IP is absent.
    true_only = {
        "True-Client-IP": "192.114.52.1",
        "X-Forwarded-For": "192.114.52.1, 172.71.195.123, 10.226.90.65",
    }
    assert client_ip(true_only, "10.193.180.8", RENDER_PROXIES) == "192.114.52.1"


def test_render_xff_skips_cloudflare_when_cf_headers_are_missing():
    # Same chain Render sends, but only X-Forwarded-For is present.
    xff = {"X-Forwarded-For": "192.114.52.1, 172.71.195.123, 10.226.90.65"}
    assert client_ip(xff, "10.193.180.8", RENDER_PROXIES) == "192.114.52.1"
    # A Cloudflare hop must not be treated as the client (the pre-fix behaviour).
    assert "172.64.0.0/13" in CLOUDFLARE_RANGES


def test_spoofed_leftmost_forwarded_hop_is_not_the_client():
    proxies = DEFAULT_TRUSTED_PROXIES + ("10.0.0.0/8",)
    # No Cloudflare client header: walk X-Forwarded-For from the right.
    headers = {"X-Forwarded-For": "203.0.113.10, 198.51.100.8"}
    assert client_ip(headers, "10.0.0.4", proxies) == "198.51.100.8"
    with_proxy_hop = {"X-Forwarded-For": "203.0.113.10, 198.51.100.8, 10.20.0.5"}
    assert client_ip(with_proxy_hop, "10.0.0.4", proxies) == "198.51.100.8"
    with_cf_hop = {"X-Forwarded-For": "203.0.113.10, 198.51.100.8, 172.71.195.123, 10.20.0.5"}
    assert client_ip(with_cf_hop, "10.0.0.4", proxies) == "198.51.100.8"


def test_forwarded_header_is_ignored_from_an_untrusted_peer():
    headers = {
        "CF-Connecting-IP": "192.114.52.1",
        "True-Client-IP": "192.114.52.1",
        "X-Forwarded-For": "192.114.52.1",
    }
    assert client_ip(headers, "203.0.113.9", DEFAULT_TRUSTED_PROXIES) == "203.0.113.9"


def test_ariel_egress_is_inside_the_registered_ranges():
    assert subnet_status("192.114.52.1", ARIEL) == "match"
    assert subnet_status("192.114.57.255", ARIEL) == "match"


def test_address_outside_ariel_is_flagged():
    assert subnet_status("8.8.8.8", ARIEL) == "mismatch"
    assert subnet_status("10.6.0.71", ARIEL) == "mismatch"
    assert subnet_status("172.71.195.123", ARIEL) == "mismatch"
    assert subnet_status("10.193.180.8", ARIEL) == "mismatch"
    assert subnet_status("192.114.52.1", ()) == "not_configured"
