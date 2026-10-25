import pytest

from kick_commenter.nlp.language import LanguageMix, LinguaGuesser


@pytest.fixture(scope="module")
def guesser() -> LinguaGuesser:
    return LinguaGuesser()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("helal olsun reis bugün çok iyi oynadın", "tr"),
        ("Lobi için takım kurması lazım", "tr"),
        ("what a play, that was insane bro", "en"),
        ("das war echt ein krasses Spiel heute", "de"),
        ("gg", None),
        ("", None),
    ],
)
def test_guess_names_the_language_or_stays_unsure(
    guesser: LinguaGuesser, text: str, expected: str | None
) -> None:
    assert guesser.guess(text) == expected


def test_guesser_needs_a_choice() -> None:
    with pytest.raises(ValueError, match="two languages"):
        LinguaGuesser(("tr",))


def test_mix_reports_shares_and_main_language() -> None:
    mix = LanguageMix()
    for language in ["tr"] * 27 + ["en"] * 3 + [None] * 5:
        mix.observe(language)

    assert mix.total == 30
    assert mix.unknown == 5
    assert mix.shares() == {"tr": 0.9, "en": 0.1}
    assert mix.dominant() == "tr"


def test_mix_waits_for_enough_evidence_and_a_clear_winner() -> None:
    mix = LanguageMix()
    assert mix.shares() == {}
    assert mix.dominant() is None

    for language in ["tr", "en"] * 20:
        mix.observe(language)

    assert mix.dominant() is None
    assert mix.dominant(min_messages=10, min_share=0.4) == "tr"
