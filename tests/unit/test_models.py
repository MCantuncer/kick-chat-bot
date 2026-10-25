from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from kick_commenter.models import ChatMessage, Sender


@given(text=st.text())
def test_chat_message_accepts_any_text_when_fields_are_valid(text: str) -> None:
    message = ChatMessage(
        message_id="m1",
        channel_id=1,
        sender=Sender(user_id=1, username="viewer"),
        text=text,
        sent_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert message.text == text


def test_chat_message_is_immutable_when_created(chat_message: ChatMessage) -> None:
    with pytest.raises(ValidationError):
        chat_message.text = "changed"  # type: ignore[misc]


def test_sender_rejects_empty_username_when_created() -> None:
    with pytest.raises(ValidationError):
        Sender(user_id=1, username="")
