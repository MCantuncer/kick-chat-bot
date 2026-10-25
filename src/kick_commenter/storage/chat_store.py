"""Local SQLite storage for collected chat messages and channel events."""

import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from kick_commenter.models import ChannelEvent, ChatMessage, Sender

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    channel_id INTEGER NOT NULL,
    sender_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    text TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    replies_to TEXT
);
CREATE INDEX IF NOT EXISTS messages_by_channel_time ON messages (channel_id, sent_at);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
"""


class ChatStore:
    """Saves chat items. Saving the same message twice is a no-op."""

    def __init__(self, path: Path) -> None:
        """Open (and create if needed) the database at ``path``."""
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)

    def save_message(self, message: ChatMessage) -> bool:
        """Store a message. Returns ``False`` when it was already stored."""
        with self._db:
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO messages VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    message.message_id,
                    message.channel_id,
                    message.sender.user_id,
                    message.sender.username,
                    message.text,
                    message.sent_at.isoformat(),
                    message.replies_to,
                ),
            )
        return cursor.rowcount == 1

    def save_event(self, event: ChannelEvent) -> None:
        """Store a channel event."""
        with self._db:
            self._db.execute(
                "INSERT INTO events (channel_id, kind, occurred_at) VALUES (?, ?, ?)",
                (event.channel_id, event.kind.value, event.occurred_at.isoformat()),
            )

    def count_messages(self, channel_id: int) -> int:
        """Return how many messages are stored for a channel."""
        row = self._db.execute(
            "SELECT COUNT(*) FROM messages WHERE channel_id = ?", (channel_id,)
        ).fetchone()
        return int(row[0])

    def count_events(self, channel_id: int) -> int:
        """Return how many events are stored for a channel."""
        row = self._db.execute(
            "SELECT COUNT(*) FROM events WHERE channel_id = ?", (channel_id,)
        ).fetchone()
        return int(row[0])

    def messages(self, channel_id: int) -> Iterator[ChatMessage]:
        """Yield a channel's stored messages, oldest first."""
        rows = self._db.execute(
            "SELECT message_id, sender_id, username, text, sent_at, replies_to "
            "FROM messages WHERE channel_id = ? ORDER BY sent_at, rowid",
            (channel_id,),
        )
        for message_id, sender_id, username, text, sent_at, replies_to in rows:
            yield ChatMessage(
                message_id=message_id,
                channel_id=channel_id,
                sender=Sender(user_id=sender_id, username=username),
                text=text,
                sent_at=datetime.fromisoformat(sent_at),
                replies_to=replies_to,
            )

    def close(self) -> None:
        """Close the database."""
        self._db.close()
