from datetime import UTC, datetime

from kick_commenter.models import ChatMessage, Sender
from kick_commenter.nlp.language import LanguageMix
from kick_commenter.nlp.pipeline import TextPipeline


class FakeGuesser:
    """Turkish for anything with three or more words, unsure otherwise."""

    def guess(self, text: str) -> str | None:
        return "tr" if len(text.split()) >= 3 else None


def message(text: str) -> ChatMessage:
    return ChatMessage(
        message_id="m",
        channel_id=1,
        sender=Sender(user_id=1, username="v"),
        text=text,
        sent_at=datetime(2026, 10, 25, tzinfo=UTC),
    )


def test_process_cleans_tags_and_tokenizes() -> None:
    pipeline = TextPipeline(FakeGuesser())

    processed = pipeline.process(message("@o2er SERHAT REİSİN TAKIMI [emote:37226:KEKW]"))

    assert processed.language == "tr"
    assert processed.tokens == ("<user>", "serhat", "reisin", "takımı", "<emote:KEKW>")
    assert processed.emotes == ("KEKW",)
    assert processed.mentions == ("o2er",)
    assert not processed.has_url
    assert not processed.is_emote_only
    assert pipeline.mix.counts["tr"] == 1


def test_short_messages_take_the_channel_language_once_it_is_clear() -> None:
    mix = LanguageMix()
    for _ in range(30):
        mix.observe("tr")
    pipeline = TextPipeline(FakeGuesser(), mix)

    processed = pipeline.process(message("GG"))

    assert processed.language == "tr"
    assert pipeline.mix.unknown == 1


def test_short_messages_stay_untagged_in_a_new_channel() -> None:
    processed = TextPipeline(FakeGuesser()).process(message("[emote:1:KEKW] [emote:2:GG]"))

    assert processed.language is None
    assert processed.is_emote_only
