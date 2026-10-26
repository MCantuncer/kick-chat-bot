import itertools
from datetime import UTC, datetime, timedelta

import pytest

from kick_commenter.engine.labels import (
    ReactionLabel,
    Signal,
    is_reaction,
    label_messages,
)
from kick_commenter.models import ChatMessage, Sender
from kick_commenter.nlp.pipeline import ProcessedMessage

START = datetime(2026, 10, 25, 20, 0, tzinfo=UTC)
_ids = itertools.count()


def said(  # noqa: PLR0913
    text: str,
    seconds: float,
    user: int,
    *,
    emotes: tuple[str, ...] = (),
    mentions: tuple[str, ...] = (),
    replies_to: str | None = None,
) -> ProcessedMessage:
    message = ChatMessage(
        message_id=f"m{next(_ids)}",
        channel_id=1,
        sender=Sender(user_id=user, username=f"user{user}"),
        text=text,
        sent_at=START + timedelta(seconds=seconds),
        replies_to=replies_to,
    )
    tokens = tuple(text.split()) + tuple(f"<emote:{e}>" for e in emotes)
    return ProcessedMessage(
        message=message,
        language="tr",
        tokens=tokens,
        emotes=emotes,
        mentions=mentions,
        has_url=False,
    )


def label_of(labels: list[ReactionLabel], target: ProcessedMessage) -> ReactionLabel:
    return next(label for label in labels if label.message is target)


def test_a_direct_reply_is_the_strongest_signal() -> None:
    question = said("reis bu oyun kaç saat sürer", 0, user=1)
    chat = [question, said("2 saat falan", 40, user=2, replies_to=question.message.message_id)]

    label = label_of(label_messages(chat), question)

    assert label.signals == {Signal.REPLY}
    assert label.score == 1.0


def test_a_mention_of_the_author_soon_after_counts() -> None:
    joke = said("bu harita labirent gibi", 0, user=1)
    chat = [joke, said("haklısın", 20, user=2, mentions=("USER1",))]

    assert label_of(label_messages(chat), joke).signals == {Signal.MENTION}


def test_a_late_mention_does_not_count() -> None:
    joke = said("bu harita labirent gibi", 0, user=1)
    chat = [joke, said("haklısın", 120, user=2, mentions=("user1",))]

    assert label_of(label_messages(chat), joke).score == 0


def test_a_laugh_burst_right_after_credits_the_message() -> None:
    joke = said("reis yine duvara sürdün", 0, user=1)
    laughs = [said("", 2 + n, user=10 + n, emotes=("KEKW",)) for n in range(3)]

    label = label_of(label_messages([joke, *laughs]), joke)

    assert label.signals == {Signal.LAUGH}
    assert label.score == 0.5


def test_a_buried_message_gets_no_credit_for_a_later_burst() -> None:
    first = said("ilk mesaj", 0, user=1)
    talk = [said(f"başka konu {n}", 1 + n, user=20 + n) for n in range(3)]
    laughs = [said("hahaha", 6 + n, user=10 + n) for n in range(3)]

    labels = label_messages([first, *talk, *laughs])

    assert label_of(labels, first).score == 0
    assert label_of(labels, talk[-1]).signals == {Signal.LAUGH}


def test_two_laughers_are_not_a_burst_and_the_author_laughing_alone_is_nothing() -> None:
    joke = said("reis yine duvara sürdün", 0, user=1)
    chat = [
        joke,
        said("", 1, user=1, emotes=("KEKW",)),
        said("hahaha", 2, user=2),
        said("sjsjsj", 3, user=3),
    ]

    assert label_of(label_messages(chat), joke).score == 0


def test_replies_from_the_author_themself_do_not_count() -> None:
    message = said("selam", 0, user=1)
    chat = [message, said("ben yine", 1, user=1, replies_to=message.message.message_id)]

    assert label_of(label_messages(chat), message).score == 0


def test_reactions_are_not_labelled_themselves() -> None:
    chat = [said("", 0, user=1, emotes=("KEKW",)), said("hahaha", 1, user=2)]

    assert label_messages(chat) == []


def test_the_score_is_the_strongest_signal_not_a_sum() -> None:
    message = said("reis bu ne", 0, user=1)
    chat = [
        message,
        said("bilmem", 1, user=2, replies_to=message.message.message_id, mentions=("user1",)),
    ]

    label = label_of(label_messages(chat), message)

    assert label.signals == {Signal.REPLY, Signal.MENTION}
    assert label.score == 1.0


def test_signals_beyond_the_reply_window_are_ignored() -> None:
    message = said("reis bu ne", 0, user=1)
    chat = [message, said("geç cevap", 600, user=2, replies_to=message.message.message_id)]

    assert label_of(label_messages(chat), message).score == 0


@pytest.mark.parametrize("text", ["hahaha", "ahahah", "sjsjsj", "jsjs", "xdxd", "lool", "lmao"])
def test_laughs_are_reactions(text: str) -> None:
    assert is_reaction(said(text, 0, user=1))


@pytest.mark.parametrize("text", ["helal reis", "haha güzeldi", "abi"])
def test_talk_is_not_a_reaction(text: str) -> None:
    assert not is_reaction(said(text, 0, user=1))


def test_emote_only_messages_are_reactions() -> None:
    assert is_reaction(said("", 0, user=1, emotes=("LUL",)))
    assert not is_reaction(said("", 0, user=1))
