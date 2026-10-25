import json
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from websockets.asyncio.server import ServerConnection, serve

from kick_commenter.collector.pusher import PusherChatSource, PusherProtocolError
from kick_commenter.models import ChannelEvent, ChannelEventKind, ChatMessage


def at(url: str) -> Callable[[], Awaitable[str]]:
    async def endpoint() -> str:
        return url

    return endpoint


async def run_server(frames: list[dict[str, Any]], received: list[dict[str, Any]]) -> Any:
    async def handler(ws: ServerConnection) -> None:
        received.append(json.loads(await ws.recv()))
        received.append(json.loads(await ws.recv()))
        for frame in frames:
            await ws.send(json.dumps(frame))
            if frame["event"] == "pusher:ping":
                received.append(json.loads(await ws.recv()))

    return await serve(handler, "127.0.0.1", 0)


async def test_stream_subscribes_answers_pings_and_yields_items(
    pusher_frames: list[dict[str, Any]],
) -> None:
    received: list[dict[str, Any]] = []
    server = await run_server(pusher_frames, received)
    port = next(iter(server.sockets)).getsockname()[1]
    source = PusherChatSource(1001, 2002, endpoint=at(f"ws://127.0.0.1:{port}"))

    items = [item async for item in source.stream()]
    server.close()

    assert [r["data"]["channel"] for r in received[:2]] == ["chatrooms.1001.v2", "channel.2002"]
    assert received[2] == {"event": "pusher:pong", "data": {}}
    messages = [i for i in items if isinstance(i, ChatMessage)]
    events = [i for i in items if isinstance(i, ChannelEvent)]
    assert [m.message_id for m in messages] == ["m-001", "m-002", "m-003", "m-002"]
    assert [e.kind for e in events] == [ChannelEventKind.SUBSCRIPTION]


async def test_stream_raises_on_error_frame() -> None:
    received: list[dict[str, Any]] = []
    server = await run_server([{"event": "pusher:error", "data": {"code": 4001}}], received)
    port = next(iter(server.sockets)).getsockname()[1]
    source = PusherChatSource(1, 2, endpoint=at(f"ws://127.0.0.1:{port}"))

    with pytest.raises(PusherProtocolError, match="4001"):
        _ = [item async for item in source.stream()]
    server.close()
