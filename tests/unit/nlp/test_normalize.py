import pytest
from hypothesis import given
from hypothesis import strategies as st

from kick_commenter.nlp.normalize import clean, lower, squeeze, tokenize, words_only


def test_clean_pulls_out_emotes_mentions_and_links() -> None:
    cleaned = clean("@o2er reis [emote:37226:KEKW] bak https://kick.com/x [emote:1:GG]")

    assert cleaned.text == "<user> reis <emote:KEKW> bak <url> <emote:GG>"
    assert cleaned.emotes == ("KEKW", "GG")
    assert cleaned.mentions == ("o2er",)
    assert cleaned.has_url
    assert words_only(cleaned) == "reis bak"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("re\u200bis", "reis"),  # zero-width space
        ("re­is", "reis"),  # soft hyphen
        ("\U0001d4fb\U0001d4ee\U0001d4f2\U0001d4fc", "reis"),  # fancy script letters
        ("ｒｅｉｓ", "reis"),  # full-width letters
        ("  reis \n\t kral  ", "reis kral"),
        ("", ""),
    ],
)
def test_clean_unifies_look_alike_text(raw: str, expected: str) -> None:
    assert clean(raw).text == expected


def test_clean_drops_stacked_accents_but_keeps_real_ones() -> None:
    zalgo = "r" + "\u0301" * 8 + "eis"

    assert clean(zalgo).text == "reis"
    assert clean("çok güzel").text == "çok güzel"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("reisssss", "reiss"), ("cooook", "cook"), ("aa", "aa"), ("1111", "1111")],
)
def test_squeeze_shortens_stretched_letters(raw: str, expected: str) -> None:
    assert squeeze(raw) == expected


def test_lower_follows_turkish_dotted_and_dotless_i() -> None:
    assert lower("TAKIM İÇİN", "tr") == "takım için"
    assert lower("TAKIM İÇİN", "en") == "takim i̇çi̇n"


def test_tokenize_keeps_placeholders_and_turkish_suffixes() -> None:
    tokens = tokenize("<user> SERHAT'IN TAKIMI 10 numara!!! <emote:KEKW>", "tr")

    assert tokens == ("<user>", "serhat'ın", "takımı", "10", "numara", "<emote:KEKW>")


@given(st.text())
def test_cleaning_any_text_is_safe_and_stable(raw: str) -> None:
    cleaned = clean(raw)

    assert clean(cleaned.text).text == cleaned.text
    assert all(token and not token.isspace() for token in tokenize(cleaned.text, "tr"))
