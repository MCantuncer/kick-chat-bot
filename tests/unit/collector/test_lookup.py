from pathlib import Path

import httpx
import pytest
import respx

from kick_commenter.collector.lookup import ChannelIds, ChannelLookup, ChannelLookupError

URL = "https://kick.com/api/v2/channels/thetoxicparty"


@pytest.fixture
async def lookup(tmp_path: Path) -> ChannelLookup:
    return ChannelLookup(httpx.AsyncClient(), tmp_path / "channels.json")


@respx.mock
async def test_resolve_reads_ids_and_caches_them(lookup: ChannelLookup) -> None:
    route = respx.get(URL).mock(
        return_value=httpx.Response(200, json={"id": 2002, "chatroom": {"id": 1001}})
    )

    first = await lookup.resolve("@TheToxicParty")
    second = await lookup.resolve("thetoxicparty")

    assert first == ChannelIds(slug="thetoxicparty", channel_id=2002, chatroom_id=1001)
    assert second == first
    assert route.call_count == 1
    assert "Mozilla" in route.calls.last.request.headers["User-Agent"]


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(404), "no channel named"),
        (httpx.Response(403), "--chatroom-id"),
        (httpx.Response(200, json={"id": 1, "chatroom": None}), "has no chatroom"),
    ],
)
@respx.mock
async def test_resolve_explains_failures(
    lookup: ChannelLookup, response: httpx.Response, message: str
) -> None:
    respx.get(URL).mock(return_value=response)

    with pytest.raises(ChannelLookupError, match=message):
        await lookup.resolve("thetoxicparty")


@respx.mock
async def test_resolve_explains_network_errors(lookup: ChannelLookup) -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectError("offline"))

    with pytest.raises(ChannelLookupError, match="could not reach"):
        await lookup.resolve("thetoxicparty")


async def test_remembered_ids_skip_the_network(lookup: ChannelLookup) -> None:
    ids = ChannelIds(slug="thetoxicparty", channel_id=2, chatroom_id=1)
    lookup.remember(ids)

    with respx.mock(assert_all_called=False):
        assert await lookup.resolve("thetoxicparty") == ids
