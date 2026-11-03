from app.net import DEFAULT_TRUSTED_PROXIES, client_ip, subnet_status

ARIEL = ("192.114.48.0/21", "192.114.56.0/23")


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


def test_spoofed_leftmost_forwarded_hop_is_not_the_client():
    proxies = DEFAULT_TRUSTED_PROXIES + ("10.0.0.0/8",)
    headers = {
        "CF-Connecting-IP": "203.0.113.10",
        "X-Forwarded-For": "203.0.113.10, 198.51.100.8",
    }
    assert client_ip(headers, "10.0.0.4", proxies) == "198.51.100.8"
    with_proxy_hop = {"X-Forwarded-For": "203.0.113.10, 198.51.100.8, 10.20.0.5"}
    assert client_ip(with_proxy_hop, "10.0.0.4", proxies) == "198.51.100.8"


def test_forwarded_header_is_ignored_from_an_untrusted_peer():
    headers = {
        "CF-Connecting-IP": "192.114.52.1",
        "X-Forwarded-For": "192.114.52.1",
    }
    assert client_ip(headers, "203.0.113.9", DEFAULT_TRUSTED_PROXIES) == "203.0.113.9"


def test_ariel_egress_is_inside_the_registered_ranges():
    assert subnet_status("192.114.52.1", ARIEL) == "match"
    assert subnet_status("192.114.57.255", ARIEL) == "match"


def test_address_outside_ariel_is_flagged():
    assert subnet_status("8.8.8.8", ARIEL) == "mismatch"
    assert subnet_status("10.6.0.71", ARIEL) == "mismatch"
    assert subnet_status("192.114.52.1", ()) == "not_configured"
