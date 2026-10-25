"""Pins the candidates built from a fixed sample chat, so changes to them are deliberate.

If a change here is intended, update the snapshot with ``pytest --snapshot-update``.
"""

from datetime import UTC, datetime
from pathlib import Path

from syrupy.assertion import SnapshotAssertion

from kick_commenter.engine.candidates import CandidateBuilder, HistoryIndex, overlap
from kick_commenter.engine.moments import Moment, MomentKind
from kick_commenter.models import ChatMessage, Sender
from kick_commenter.nlp.language import LinguaGuesser
from kick_commenter.nlp.pipeline import ProcessedMessage, TextPipeline
from kick_commenter.profile.builder import ProfileBuilder

FIXTURE = Path(__file__).parent.parent / "fixtures" / "community_chat.txt"
NOW = datetime(2026, 10, 25, 23, 0, tzinfo=UTC)


def sample_chat(pipeline: TextPipeline) -> list[ProcessedMessage]:
    return [
        pipeline.process(
            ChatMessage(
                message_id=str(n),
                channel_id=1,
                sender=Sender(user_id=n % 17, username=f"viewer_{n % 17}"),
                text=line,
                sent_at=NOW,
            )
        )
        for n, line in enumerate(FIXTURE.read_text(encoding="utf-8").splitlines())
    ]


def test_sample_chat_candidates_are_stable(snapshot: SnapshotAssertion) -> None:
    pipeline = TextPipeline(LinguaGuesser())
    chat = sample_chat(pipeline)
    builder = ProfileBuilder("sample", pipeline.mix)
    for processed in chat:
        builder.add(processed)
    candidates = CandidateBuilder(
        profile=builder.build(NOW),
        index=HistoryIndex(chat),
        sendable_emotes=frozenset({"KEKW", "LUL"}),
    )
    recent = chat[-60:]

    built = {
        kind.value: [
            (c.text, c.source.value)
            for c in candidates.build(
                Moment(kind=kind, at=NOW, context=tuple(chat[-5:]), trigger=chat[-1]),
                recent_chat=recent,
            )
        ]
        for kind in MomentKind
        if kind is not MomentKind.QUESTION
    }

    assert built == snapshot
    # Whatever the exact picks, these rules hold for every candidate.
    for picks in built.values():
        assert picks, "every moment kind gets something to say"
        for text, _ in picks:
            assert all(overlap(text.split(), p.message.text.split()) <= 0.5 for p in recent)
