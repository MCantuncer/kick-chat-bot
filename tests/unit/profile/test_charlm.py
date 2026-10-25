import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kick_commenter.profile.charlm import END, CharModel


@pytest.fixture
def model() -> CharModel:
    trained = CharModel(order=4)
    for text in ["helal olsun reis", "reis bugün başka", "aynen reis", "helal olsun kral"] * 5:
        trained.train(text)
    return trained


def test_text_in_the_chat_style_is_less_surprising(model: CharModel) -> None:
    assert model.is_trained
    assert model.perplexity("helal reis") < model.perplexity("quantum physics")


@given(history=st.text(alphabet="helo rsibuügnşkayd", max_size=5))
def test_probabilities_add_up_to_one(history: str) -> None:
    model = CharModel(order=3)
    for text in ["helal olsun reis", "reis bugün başka", "aynen kral"]:
        model.train(text)
    alphabet = set("helal olsun reis bugün başka aynen kral") | {END}

    total = sum(model.probability(c, history) for c in alphabet)
    unseen = model.probability("☃", history)

    assert unseen > 0
    assert math.isclose(total + unseen, 1.0, rel_tol=1e-9)


def test_untrained_model_treats_everything_alike() -> None:
    model = CharModel(order=2)

    assert not model.is_trained
    assert math.isclose(model.probability("a", ""), 0.5)


def test_order_must_be_positive() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        CharModel(order=0)


def test_order_one_ignores_history() -> None:
    model = CharModel(order=1)
    model.train("aab")

    assert model.probability("a", "zzz") == model.probability("a", "")
