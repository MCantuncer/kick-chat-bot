"""Reads a channel's chat from the public live stream the kick.com website uses.

This stream is not part of Kick's official API. It is read-only and needs no
login. If Kick changes it, only this adapter needs updating.
"""

import json
import logging
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

from websockets.asyncio.client import ClientConnection, connect

from kick_commenter.collector.source import ChatItem
from kick_commenter.models import ChannelEvent, ChannelEventKind, ChatMessage, Sender

logger = logging.getLogger(__name__)

PUSHER_URL = (
    "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679"
    "?protocol=7&client=js&version=8.4.0&flash=false"
)
CHAT_MESSAGE_EVENT = "App\\Events\\ChatMessageEvent"

# Channel event names as the website receives them. Unknown names are ignored.
CHANNEL_EVENTS = {
    "App\\Events\\SubscriptionEvent": ChannelEventKind.SUBSCRIPTION,
    "App\\Events\\GiftedSubscriptionsEvent": ChannelEventKind.GIFTED_SUBSCRIPTIONS,
    "App\\Events\\StreamHostEvent": ChannelEventKind.RAID,
    "App\\Events\\StreamerIsLive": ChannelEventKind.STREAM_STARTED,
    "App\\Events\\StopStreamBroadcast": ChannelEventKind.STREAM_ENDED,
}

Connector = Callable[[str], Any]


class PusherProtocolError(Exception):
    """The stream sent an error or something we cannot understand."""


class PusherChatSource:
    """Chat source for one channel, identified by its chatroom and channel ids."""

    def __init__(
        self,
        chatroom_id: int,
        channel_id: int,
        *,
        url: str = PUSHER_URL,
        connector: Connector = connect,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Read chatroom ``chatroom_id`` and events of channel ``channel_id``."""
        self._chatroom_id = chatroom_id
        self._channel_id = channel_id
        self._url = url
        self._connector = connector
        self._clock = clock

    async def stream(self) -> AsyncIterator[ChatItem]:
        """Connect, subscribe and yield items until the connection closes."""
        async with self._connector(self._url) as ws:
            await self._subscribe(ws, f"chatrooms.{self._chatroom_id}.v2")
            await self._subscribe(ws, f"channel.{self._channel_id}")
            async for raw in ws:
                item = await self._handle(ws, raw)
                if item is not None:
                    yield item

    async def _subscribe(self, ws: ClientConnection, channel: str) -> None:
        await ws.send(
            json.dumps({"event": "pusher:subscribe", "data": {"auth": "", "channel": channel}})
        )

    async def _handle(self, ws: ClientConnection, raw: str | bytes) -> ChatItem | None:
        envelope = json.loads(raw)
        event = envelope.get("event", "")
        if event == "pusher:ping":
            await ws.send(json.dumps({"event": "pusher:pong", "data": {}}))
            return None
        if event == "pusher:error":
            msg = f"stream error: {envelope.get('data')}"
            raise PusherProtocolError(msg)
        if event == CHAT_MESSAGE_EVENT:
            return parse_chat_message(_inner(envelope), self._channel_id)
        if event in CHANNEL_EVENTS:
            return ChannelEvent(
                channel_id=self._channel_id,
                kind=CHANNEL_EVENTS[event],
                occurred_at=self._clock(),
            )
        logger.debug("ignoring stream event %s", event)
        return None


def parse_chat_message(data: dict[str, Any], channel_id: int) -> ChatMessage | None:
    """Map a stream chat payload to a ``ChatMessage``. Returns ``None`` for empty ones."""
    content = data.get("content") or ""
    sender = data.get("sender") or {}
    if not content or "id" not in sender:
        return None
    original = (data.get("metadata") or {}).get("original_message") or {}
    return ChatMessage(
        message_id=str(data["id"]),
        channel_id=channel_id,
        sender=Sender(user_id=int(sender["id"]), username=sender.get("username") or "unknown"),
        text=content,
        sent_at=datetime.fromisoformat(data["created_at"]),
        replies_to=str(original["id"]) if original.get("id") else None,
    )


def _inner(envelope: dict[str, Any]) -> dict[str, Any]:
    # The stream double-encodes payloads: "data" is a JSON string.
    data = envelope.get("data")
    parsed = json.loads(data) if isinstance(data, str) else data
    if not isinstance(parsed, dict):
        msg = "chat payload is not an object"
        raise PusherProtocolError(msg)
    return parsed
