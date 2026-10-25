"""Guards the shape of shared models. A failure here means a breaking contract change."""

from kick_commenter.models import ChannelEvent, ChannelEventKind, ChatMessage, Sender


def test_chat_message_fields_are_stable() -> None:
    assert list(ChatMessage.model_fields) == [
        "message_id",
        "channel_id",
        "sender",
        "text",
        "sent_at",
        "replies_to",
    ]


def test_sender_fields_are_stable() -> None:
    assert list(Sender.model_fields) == ["user_id", "username"]


def test_channel_event_fields_are_stable() -> None:
    assert list(ChannelEvent.model_fields) == ["channel_id", "kind", "occurred_at", "actor"]


def test_channel_event_kinds_are_stable() -> None:
    assert {kind.value for kind in ChannelEventKind} == {
        "follow",
        "subscription",
        "gifted_subscriptions",
        "raid",
        "kicks_gifted",
        "stream_started",
        "stream_ended",
    }


def test_chat_message_round_trips_through_json(chat_message: ChatMessage) -> None:
    assert ChatMessage.model_validate_json(chat_message.model_dump_json()) == chat_message
