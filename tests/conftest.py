from datetime import UTC, datetime

import pytest

from kick_commenter.models import ChatMessage, Sender


@pytest.fixture
def sender() -> Sender:
    return Sender(user_id=1, username="viewer")


@pytest.fixture
def chat_message(sender: Sender) -> ChatMessage:
    return ChatMessage(
        message_id="m1",
        channel_id=42,
        sender=sender,
        text="reis bugün başka",
        sent_at=datetime(2026, 10, 25, 20, 0, tzinfo=UTC),
    )
