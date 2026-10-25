import pytest
from hypothesis import given
from hypothesis import strategies as st

from kick_commenter.engine.safety import (
    Reason,
    SafetyFilter,
    comparable_words,
    honest_answer,
    is_bot_question,
)

check = SafetyFilter().check

# Everyday chat the bot should be free to say.
SAFE_LINES = [
    "helal olsun reis",
    "aynen kral KEKW",
    "abi bugün başka oynuyorsun",
    "sıkıntı yok reis devam",
    "götür bizi finale",
    "parti başlasın",
    "gg wp",
    "let's go chat",
    "nice clutch",
    "bu oyun efsane",
    "class act",
    "yarası olan gocunsun",
]
SAFE_WORDS = ["reis", "kral", "abi", "helal", "olsun", "aynen", "gg", "efsane", "devam", "güzel"]


@pytest.mark.parametrize("line", SAFE_LINES)
def test_everyday_chat_passes(line: str) -> None:
    assert check(line).allowed


@pytest.mark.parametrize(
    "line",
    [
        "siktir git",
        "SİKTİR",
        "SIKTIR",
        "s1kt1r",
        "s i k t i r",
        "s.i.k.t.i.r",
        "siiiiktir",
        "si\u200bktir",
        "orospu",
        "0r0spu",
        "amk",
        "AMK reis",
        "fuck",
        "f u c k",
        "fuuuuck",
        "ｆｕｃｋ",
        "you bitch",
        "salak mısın",
    ],
)
def test_abuse_is_caught_through_disguises(line: str) -> None:
    assert check(line).reason is Reason.ABUSE


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        ("seçim yaklaşıyor", Reason.TOPIC),
        ("bahis sitesi var mı", Reason.TOPIC),
        ("bitcoin almak lazım", Reason.TOPIC),
        ("who will win the election", Reason.TOPIC),
        ("çok güzelsin", Reason.LOOKS),
        ("so cute", Reason.LOOKS),
        ("ben de dün maça gittim", Reason.PERSONAL),
        ("25 yaşındayım", Reason.PERSONAL),
        ("bot değilim ya", Reason.PERSONAL),
        ("I'm not a bot", Reason.PERSONAL),
        ("my wife said so", Reason.PERSONAL),
        ("kaç yaşındasın", Reason.PERSONAL),
    ],
)
def test_off_limits_topics_and_made_up_lives(line: str, reason: Reason) -> None:
    assert check(line).reason is reason


@pytest.mark.parametrize(
    "line",
    ["bak https://site.com", "www.site.com", "site.com'a gir", "discord.gg/abc", "site . com"],
)
def test_links_are_never_posted(line: str) -> None:
    assert check(line).reason is Reason.LINK


def test_mentions_only_of_people_who_spoke_to_the_bot() -> None:
    assert check("@o2er selam").reason is Reason.MENTION
    assert check("@o2er selam", addressed_by=["O2ER"]).allowed


def test_empty_and_long_messages_are_dropped() -> None:
    assert check("   ").reason is Reason.EMPTY
    assert check("\u200b").reason is Reason.EMPTY
    assert check("reis " * 50).reason is Reason.TOO_LONG


def test_bot_questions_are_recognised() -> None:
    assert is_bot_question("sen bot musun")
    assert is_bot_question("golfwangtr botmusun")
    assert is_bot_question("are you a bot?")
    assert not is_bot_question("bottan iyi oynuyor")


def test_the_honest_answer_is_friendly_truthful_and_passes_the_filters() -> None:
    for language in ("tr", "en", None, "de"):
        answer = honest_answer(language)
        assert "bot" in answer
        assert check(answer).allowed
    assert honest_answer("tr").startswith("evet")


def test_single_letter_runs_are_joined() -> None:
    assert "sik" in comparable_words("s . i . k")
    assert "reis" in comparable_words("r e i s abi")


@given(st.lists(st.sampled_from(SAFE_WORDS), min_size=1, max_size=8))
def test_any_mix_of_everyday_words_passes(words: list[str]) -> None:
    assert check(" ".join(words)).allowed


@given(
    before=st.lists(st.sampled_from(SAFE_WORDS), max_size=4),
    after=st.lists(st.sampled_from(SAFE_WORDS), max_size=4),
    word=st.sampled_from(["siktir", "orospu", "amk", "fuck", "bitch", "yarrak"]),
    disguise=st.sampled_from(["plain", "upper", "spaced", "dotted", "leet", "stretched", "hidden"]),
)
def test_abuse_never_passes_whatever_surrounds_or_disguises_it(
    before: list[str], after: list[str], word: str, disguise: str
) -> None:
    disguised = {
        "plain": word,
        "upper": word.upper(),
        "spaced": " ".join(word),
        "dotted": ".".join(word),
        "leet": word.replace("o", "0").replace("i", "1"),
        "stretched": word[0] + word[1] * 4 + word[2:],
        "hidden": word[0] + "\u200b" + word[1:],
    }[disguise]

    assert check(" ".join([*before, disguised, *after])).reason is Reason.ABUSE
