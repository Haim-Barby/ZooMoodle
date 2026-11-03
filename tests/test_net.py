from app.net import DEFAULT_TRUSTED_PROXIES, client_ip, subnet_status

ARIEL = ("192.114.48.0/21", "192.114.56.0/23")


def test_forwarded_header_is_trusted_from_loopback():
    headers = {
        "CF-Connecting-IP": "192.114.52.1",
        "X-Forwarded-For": "198.51.100.9, 127.0.0.1",
    }
    assert client_ip(headers, "127.0.0.1", DEFAULT_TRUSTED_PROXIES) == "192.114.52.1"
    assert client_ip(headers, "::1", DEFAULT_TRUSTED_PROXIES) == "192.114.52.1"
    xff_only = {"X-Forwarded-For": "192.114.52.1, 203.0.113.4"}
    assert client_ip(xff_only, "127.0.0.1", DEFAULT_TRUSTED_PROXIES) == "192.114.52.1"


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
