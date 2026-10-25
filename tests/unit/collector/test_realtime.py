import json

import httpx
import pytest
import respx

from kick_commenter.collector.realtime import FALLBACK_APP, PusherApp, RealtimeConfig

URL = "https://web.kick.com/api/v1/realtime/channels/2002/chat/connection"


def connections(*entries: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, json={"data": {"connections": list(entries)}})


@pytest.fixture
async def realtime() -> RealtimeConfig:
    return RealtimeConfig(httpx.AsyncClient())


@respx.mock
async def test_uses_the_app_kick_offers(realtime: RealtimeConfig) -> None:
    route = respx.post(URL).mock(
        return_value=connections(
            {"provider": "centrifugo", "credentials": {"url": "wss://elsewhere"}},
            {"provider": "pusher", "credentials": {"app_key": "newkey", "cluster": "eu"}},
        )
    )

    app = await realtime.pusher_app(2002)

    assert app == PusherApp(app_key="newkey", cluster="eu")
    assert app.url.startswith("wss://ws-eu.pusher.com/app/newkey?protocol=7")
    sent = json.loads(route.calls.last.request.content)
    assert sent["capabilities"]["accepted_providers"] == [{"provider": "pusher"}]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, text="not json"),
        connections({"provider": "centrifugo"}),
        connections({"provider": "pusher", "credentials": {"app_key": "", "cluster": "us2"}}),
    ],
)
@respx.mock
async def test_falls_back_to_the_known_app(
    realtime: RealtimeConfig, response: httpx.Response
) -> None:
    respx.post(URL).mock(return_value=response)

    assert await realtime.pusher_app(2002) == FALLBACK_APP


@respx.mock
async def test_falls_back_when_kick_is_unreachable(realtime: RealtimeConfig) -> None:
    respx.post(URL).mock(side_effect=httpx.ConnectError("offline"))

    assert await realtime.pusher_app(2002) == FALLBACK_APP


def test_fallback_is_not_the_retired_key() -> None:
    assert FALLBACK_APP.app_key != "32cbd69e4b950bf97679"
