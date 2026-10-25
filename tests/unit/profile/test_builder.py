from datetime import UTC, datetime
from pathlib import Path

from kick_commenter.models import ChatMessage, Sender
from kick_commenter.nlp.pipeline import TextPipeline
from kick_commenter.profile.builder import CommunityProfile, ProfileBuilder, everyday_language

NOW = datetime(2026, 10, 25, 23, 0, tzinfo=UTC)


class Turkish:
    def guess(self, text: str) -> str | None:
        return "tr" if text else None


def build(lines: list[str]) -> tuple[ProfileBuilder, CommunityProfile]:
    pipeline = TextPipeline(Turkish())
    builder = ProfileBuilder("thetoxicparty", pipeline.mix)
    for n, line in enumerate(lines):
        message = ChatMessage(
            message_id=str(n),
            channel_id=1,
            sender=Sender(user_id=n, username=f"v{n}"),
            text=line,
            sent_at=NOW,
        )
        builder.add(pipeline.process(message))
    return builder, builder.build(NOW, background=lambda _word: 0.0001)


def test_profile_brings_together_words_phrases_nicknames_and_style() -> None:
    lines = ["helal olsun reis", "reis bugün başka", "aynen reis", "[emote:1:KEKW]"] * 10

    builder, profile = build(lines)

    assert profile.channel == "thetoxicparty"
    assert profile.messages == 40
    assert profile.main_language == "tr"
    assert profile.languages == {"tr": 1.0}
    assert profile.words[0].term == "reis"
    assert "helal olsun" in {p.term for p in profile.phrases}
    assert [t.term for t in profile.address_terms] == ["reis"]
    assert profile.style.top_emotes == [("KEKW", 10)]
    assert builder.char_model.perplexity("helal reis") < builder.char_model.perplexity("xyzzy")


def test_profile_round_trips_through_a_file(tmp_path: Path) -> None:
    _, profile = build(["helal olsun reis"] * 5)
    path = tmp_path / "profiles" / "thetoxicparty.json"

    profile.save(path)

    assert CommunityProfile.load(path) == profile


def test_everyday_language_knows_common_words() -> None:
    turkish = everyday_language("tr")
    fallback = everyday_language(None)

    assert turkish("için") > turkish("reis") > turkish("kekw") == 0
    assert fallback("the") > 0
