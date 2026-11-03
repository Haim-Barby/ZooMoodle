import asyncio
import base64

import httpx

from app.main import create_app
from app.net import DEFAULT_TRUSTED_PROXIES, client_ip
from tests.conftest import make_device, make_settings

TOKEN = "lecturer-test-token"
RENDER_PROXIES = DEFAULT_TRUSTED_PROXIES + ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")


async def _check_in(client, room_id, device, student_id, code, headers):
    opened = await client.post(
        f"/api/rooms/{room_id}/challenge",
        headers=headers,
        json={"student_id": student_id, "device_id": device["device_id"], "public_jwk": device["jwk"]},
    )
    assert opened.status_code == 200, opened.text
    body = opened.json()
    signature = base64.b64encode(device["sign"](body["challenge_id"], body["nonce"])).decode()
    checked = await client.post(
        f"/api/rooms/{room_id}/checkin",
        headers=headers,
        json={
            "challenge_id": body["challenge_id"],
            "signature": signature,
            "mode": "in_class",
            "token_code": code,
            "seat_zone": "front-left",
            "student_name": student_id,
        },
    )
    assert checked.status_code == 200, checked.text
    return checked.json()


def _transport(app, peer):
    return httpx.ASGITransport(app=app, client=(peer, 1234))


def test_shared_proxy_address_does_not_merge_devices():
    app = create_app(make_settings())

    async def scenario():
        async with httpx.AsyncClient(transport=_transport(app, "10.0.0.4"), base_url="http://test") as client:
            room = (await client.post(
                "/api/rooms",
                headers={"x-lecturer-token": TOKEN},
                json={"title": "Lesson"},
            )).json()
            code = (await client.get(
                f"/api/rooms/{room['id']}/token",
                headers={"x-lecturer-token": TOKEN},
            )).json()["code"]
            headers = {"x-forwarded-for": "203.0.113.10", "cf-connecting-ip": "203.0.113.10"}
            first = await _check_in(client, room["id"], make_device(), "stu-1", code, headers)
            second = await _check_in(client, room["id"], make_device(), "stu-2", code, headers)
        return first, second

    first, second = asyncio.run(scenario())
    assert "shared_device" not in first["flags"]
    assert "shared_device" not in second["flags"]
    assert first["subnet"] == "not_configured"
    assert second["subnet"] == "not_configured"


def test_private_render_proxy_uses_the_client_hop_for_subnet():
    app = create_app(make_settings(allowed_subnets=("203.0.113.10/32",), trusted_proxies=RENDER_PROXIES))

    async def scenario():
        async with httpx.AsyncClient(transport=_transport(app, "10.0.0.4"), base_url="http://test") as client:
            room = (await client.post(
                "/api/rooms",
                headers={"x-lecturer-token": TOKEN},
                json={"title": "Lesson"},
            )).json()
            code = (await client.get(
                f"/api/rooms/{room['id']}/token",
                headers={"x-lecturer-token": TOKEN},
            )).json()["code"]
            on_campus = await _check_in(
                client,
                room["id"],
                make_device(),
                "stu-1",
                code,
                {"x-forwarded-for": "203.0.113.10, 10.0.0.4"},
            )
            off_campus = await _check_in(
                client,
                room["id"],
                make_device(),
                "stu-2",
                code,
                {"x-forwarded-for": "198.51.100.8, 10.0.0.4"},
            )
        return on_campus, off_campus

    on_campus, off_campus = asyncio.run(scenario())
    assert on_campus["subnet"] == "match"
    assert off_campus["subnet"] == "mismatch"
    assert "shared_device" not in on_campus["flags"]
    assert "shared_device" not in off_campus["flags"]


def test_rewritten_client_peer_ignores_a_spoofed_forwarded_header():
    # Uvicorn with FORWARDED_ALLOW_IPS=* replaces the peer with the first hop.
    # That peer is the client, so a second header must not override it.
    assert client_ip(
        {"cf-connecting-ip": "203.0.113.10", "x-forwarded-for": "203.0.113.10"},
        "198.51.100.8",
        DEFAULT_TRUSTED_PROXIES,
    ) == "198.51.100.8"
    app = create_app(make_settings(allowed_subnets=("203.0.113.10/32",)))

    async def scenario():
        async with httpx.AsyncClient(transport=_transport(app, "198.51.100.8"), base_url="http://test") as client:
            room = (await client.post(
                "/api/rooms",
                headers={"x-lecturer-token": TOKEN},
                json={"title": "Lesson"},
            )).json()
            code = (await client.get(
                f"/api/rooms/{room['id']}/token",
                headers={"x-lecturer-token": TOKEN},
            )).json()["code"]
            return await _check_in(
                client,
                room["id"],
                make_device(),
                "stu-1",
                code,
                {"cf-connecting-ip": "203.0.113.10", "x-forwarded-for": "203.0.113.10"},
            )

    checked = asyncio.run(scenario())
    assert checked["subnet"] == "mismatch"
