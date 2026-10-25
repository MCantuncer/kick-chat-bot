"""Pins the profile learned from a fixed sample chat, so changes to it are deliberate.

If a change here is intended, update the snapshot with ``pytest --snapshot-update``.
"""

from datetime import UTC, datetime
from pathlib import Path

from syrupy.assertion import SnapshotAssertion

from kick_commenter.models import ChatMessage, Sender
from kick_commenter.nlp.language import LinguaGuesser
from kick_commenter.nlp.pipeline import TextPipeline
from kick_commenter.profile.builder import ProfileBuilder

FIXTURE = Path(__file__).parent.parent / "fixtures" / "community_chat.txt"
NOW = datetime(2026, 10, 25, 23, 0, tzinfo=UTC)


def test_sample_chat_profile_is_stable(snapshot: SnapshotAssertion) -> None:
    pipeline = TextPipeline(LinguaGuesser())
    builder = ProfileBuilder("sample", pipeline.mix)
    for n, line in enumerate(FIXTURE.read_text(encoding="utf-8").splitlines()):
        message = ChatMessage(
            message_id=str(n),
            channel_id=1,
            sender=Sender(user_id=n % 17, username=f"viewer_{n % 17}"),
            text=line,
            sent_at=NOW,
        )
        builder.add(pipeline.process(message))

    profile = builder.build(NOW)

    assert profile.model_dump(mode="json") == snapshot
    # What any sensible profile of this chat must contain, whatever the exact scores.
    assert profile.main_language == "tr"
    assert {"reis", "kral", "abi"} <= {t.term for t in profile.address_terms}
    assert "helal olsun" in {p.term for p in profile.phrases}
    assert profile.style.top_emotes[0][0] == "KEKW"
