import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from kick_commenter.models import ChatMessage, Sender

FIXTURES = Path(__file__).parent / "fixtures"


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


@pytest.fixture
def pusher_frames() -> list[dict[str, Any]]:
    lines = (FIXTURES / "pusher_frames.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]
