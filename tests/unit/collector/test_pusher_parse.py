import json
from datetime import UTC, datetime
from typing import Any

from kick_commenter.collector.pusher import CHAT_MESSAGE_EVENT, parse_chat_message


def chat_payloads(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [json.loads(f["data"]) for f in frames if f["event"] == CHAT_MESSAGE_EVENT]


def test_parse_maps_stream_payload_to_chat_message(pusher_frames: list[dict[str, Any]]) -> None:
    message = parse_chat_message(chat_payloads(pusher_frames)[0], channel_id=2002)

    assert message is not None
    assert message.message_id == "m-001"
    assert message.channel_id == 2002
    assert (message.sender.user_id, message.sender.username) == (11, "viewer_a")
    assert message.text == "reis bugün başka [emote:37226:KEKW]"
    assert message.sent_at == datetime(2026, 10, 25, 20, 0, 1, tzinfo=UTC)
    assert message.replies_to is None


def test_parse_keeps_reply_target(pusher_frames: list[dict[str, Any]]) -> None:
    message = parse_chat_message(chat_payloads(pusher_frames)[2], channel_id=2002)

    assert message is not None
    assert message.replies_to == "m-002"


def test_parse_skips_empty_messages(pusher_frames: list[dict[str, Any]]) -> None:
    assert parse_chat_message(chat_payloads(pusher_frames)[3], channel_id=2002) is None


def test_parse_skips_payload_without_sender() -> None:
    payload = {"id": "x", "content": "hi", "created_at": "2026-10-25T20:00:00+00:00"}

    assert parse_chat_message(payload, channel_id=1) is None
