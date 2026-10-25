from datetime import UTC, datetime
from pathlib import Path

from kick_commenter.models import ChannelEvent, ChannelEventKind, ChatMessage
from kick_commenter.storage.chat_store import ChatStore


def test_saving_same_message_twice_stores_it_once(
    tmp_path: Path, chat_message: ChatMessage
) -> None:
    store = ChatStore(tmp_path / "db" / "chat.sqlite3")

    assert store.save_message(chat_message) is True
    assert store.save_message(chat_message) is False
    assert store.count_messages(chat_message.channel_id) == 1
    store.close()


def test_messages_persist_after_reopening(tmp_path: Path, chat_message: ChatMessage) -> None:
    path = tmp_path / "chat.sqlite3"
    first = ChatStore(path)
    first.save_message(chat_message)
    first.close()

    second = ChatStore(path)

    assert second.count_messages(chat_message.channel_id) == 1
    assert second.count_messages(999) == 0
    second.close()


def test_events_are_stored_per_channel(tmp_path: Path) -> None:
    store = ChatStore(tmp_path / "chat.sqlite3")
    event = ChannelEvent(
        channel_id=5, kind=ChannelEventKind.RAID, occurred_at=datetime(2026, 1, 1, tzinfo=UTC)
    )

    store.save_event(event)
    store.save_event(event)

    assert store.count_events(5) == 2
    assert store.count_events(6) == 0
    store.close()


def test_messages_come_back_oldest_first(tmp_path: Path, chat_message: ChatMessage) -> None:
    store = ChatStore(tmp_path / "chat.sqlite3")
    later = chat_message.model_copy(
        update={"message_id": "m2", "sent_at": datetime(2026, 10, 25, 21, 0, tzinfo=UTC)}
    )
    store.save_message(later)
    store.save_message(chat_message)

    assert list(store.messages(chat_message.channel_id)) == [chat_message, later]
    assert list(store.messages(999)) == []
    store.close()
