from datetime import UTC, datetime

from kick_commenter.models import ChatMessage, Sender
from kick_commenter.nlp.pipeline import TextPipeline
from kick_commenter.profile.style import StyleCounter


class Turkish:
    def guess(self, _text: str) -> str | None:
        return "tr"


def processed(text: str, replies_to: str | None = None) -> object:
    message = ChatMessage(
        message_id=text,
        channel_id=1,
        sender=Sender(user_id=1, username="v"),
        text=text,
        sent_at=datetime(2026, 10, 25, tzinfo=UTC),
        replies_to=replies_to,
    )
    return TextPipeline(Turkish()).process(message)


def test_style_shares_count_each_kind_of_message() -> None:
    counter = StyleCounter()
    for text, reply in [
        ("ADAM YAPTI YİNE", None),
        ("helaaal olsun reis 😂", None),
        ("yayın kaçta?", None),
        ("[emote:1:KEKW] [emote:1:KEKW]", None),
        ("@o2er aynen!", "m0"),
    ]:
        counter.add(processed(text, reply))  # type: ignore[arg-type]

    summary = counter.summary()

    assert summary.messages == 5
    assert summary.caps_share == 0.2
    assert summary.emoji_share == 0.2
    assert summary.question_share == 0.2
    assert summary.exclamation_share == 0.2
    assert summary.stretched_share == 0.2
    assert summary.emote_share == 0.2
    assert summary.emote_only_share == 0.2
    assert summary.mention_share == 0.2
    assert summary.reply_share == 0.2
    assert summary.top_emotes == [("KEKW", 2)]
    assert summary.median_words == 2
    assert summary.long_message_words == 3


def test_empty_style_is_all_zero() -> None:
    summary = StyleCounter().summary()

    assert summary.messages == 0
    assert summary.median_words == 0
    assert summary.caps_share == 0
