"""Pins how the text pipeline reads messy chat, so changes to it are deliberate.

If a change here is intended, update the snapshot with ``pytest --snapshot-update``.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from syrupy.assertion import SnapshotAssertion

from kick_commenter.models import ChatMessage, Sender
from kick_commenter.nlp.language import LinguaGuesser
from kick_commenter.nlp.pipeline import TextPipeline

FIXTURE = Path(__file__).parent.parent / "fixtures" / "messy_chat.txt"


def test_messy_chat_is_read_consistently(snapshot: SnapshotAssertion) -> None:
    pipeline = TextPipeline(LinguaGuesser())
    results: list[dict[str, Any]] = []
    for n, line in enumerate(FIXTURE.read_text(encoding="utf-8").splitlines()):
        message = ChatMessage(
            message_id=str(n),
            channel_id=1,
            sender=Sender(user_id=1, username="viewer"),
            text=line,
            sent_at=datetime(2026, 10, 25, tzinfo=UTC),
        )
        processed = pipeline.process(message)
        results.append(
            {
                "text": line,
                "language": processed.language,
                "tokens": list(processed.tokens),
                "emote_only": processed.is_emote_only,
            }
        )

    assert results == snapshot
