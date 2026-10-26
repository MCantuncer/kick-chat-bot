import itertools
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from kick_commenter.engine.labels import ReactionLabel, Signal
from kick_commenter.engine.ranker import Featurizer, LogisticRanker, training_samples
from kick_commenter.models import ChatMessage, Sender
from kick_commenter.nlp.pipeline import ProcessedMessage
from kick_commenter.profile.builder import CommunityProfile
from kick_commenter.profile.style import StyleSummary
from kick_commenter.profile.terms import ScoredTerm

START = datetime(2026, 10, 25, 20, 0, tzinfo=UTC)
_ids = itertools.count()


def term(text: str) -> ScoredTerm:
    return ScoredTerm(term=text, count=10, score=3.0)


PROFILE = CommunityProfile(
    channel="thetoxicparty",
    built_at=START,
    messages=500,
    languages={"tr": 1.0},
    main_language="tr",
    words=[term("reis"), term("kral"), term("helal")],
    phrases=[term("helal olsun")],
    address_terms=[term("reis"), term("kral")],
    style=StyleSummary(
        messages=500,
        median_words=3,
        long_message_words=10,
        caps_share=0.1,
        emoji_share=0.0,
        emote_share=0.3,
        emote_only_share=0.1,
        question_share=0.1,
        exclamation_share=0.1,
        stretched_share=0.1,
        mention_share=0.1,
        reply_share=0.1,
        top_emotes=[("KEKW", 40)],
    ),
)
FEATURIZER = Featurizer.from_profile(PROFILE)


def said(text: str, seconds: float = 0, emotes: tuple[str, ...] = ()) -> ProcessedMessage:
    message = ChatMessage(
        message_id=f"m{next(_ids)}",
        channel_id=1,
        sender=Sender(user_id=1, username="viewer"),
        text=text,
        sent_at=START + timedelta(seconds=seconds),
    )
    return ProcessedMessage(
        message=message,
        language="tr",
        tokens=tuple(text.lower().split()) + tuple(f"<emote:{e}>" for e in emotes),
        emotes=emotes,
        mentions=(),
        has_url=False,
    )


def test_features_describe_community_style() -> None:
    features = FEATURIZER.features(said("helal olsun reis", emotes=("KEKW",)))

    assert features["community_words"] == 2 / 3
    assert features["phrase"] == 1.0
    assert features["address"] == 1.0
    assert features["emote"] == 1.0
    assert features["usual_length"] == 1.0
    assert features["long"] == 0.0


def test_features_for_an_unusual_message() -> None:
    text = "BU OYUN NEDEN BU KADAR UZUN SÜRÜYOR BİR TÜRLÜ BİTMİYOR ACABA NE ZAMAN?"
    features = FEATURIZER.features(said(text), gap=timedelta(seconds=60))

    assert features["community_words"] == 0.0
    assert features["phrase"] == 0.0
    assert features["question"] == 1.0
    assert features["long"] == 1.0
    assert features["shouting"] == 1.0
    assert features["usual_length"] < 0.5
    assert features["slow_chat"] == 1.0


def test_empty_message_features_are_safe() -> None:
    features = FEATURIZER.features(said("", emotes=("KEKW",)))

    assert features["community_words"] == 0.0
    assert all(math.isfinite(v) for v in features.values())


def test_training_samples_carry_scores_and_gaps() -> None:
    labels = [
        ReactionLabel(said("helal reis", 0), frozenset({Signal.REPLY})),
        ReactionLabel(said("bilmem", 20)),
    ]

    samples = training_samples(labels, FEATURIZER)

    assert [score for _, score in samples] == [1.0, 0.0]
    assert samples[0][0]["slow_chat"] == 0.0
    assert samples[1][0]["slow_chat"] == 20 / 30


def test_the_ranker_learns_which_feature_goes_with_landing() -> None:
    # Hand-built chat where the answer is obvious: community-flavoured
    # messages get answered, generic ones don't.
    landed = [{"address": 1.0, "emote": 0.0}, {"address": 1.0, "emote": 1.0}] * 20
    ignored = [{"address": 0.0, "emote": 0.0}, {"address": 0.0, "emote": 1.0}] * 20
    samples = [(f, 1.0) for f in landed] + [(f, 0.0) for f in ignored]

    ranker = LogisticRanker().fit(samples)

    assert ranker.weights["address"] > 1.0
    assert abs(ranker.weights["emote"]) < 0.5
    assert ranker.predict({"address": 1.0}) > 0.7
    assert ranker.predict({"address": 0.0}) < 0.3


def test_training_is_repeatable() -> None:
    samples = [({"address": 1.0}, 1.0), ({"address": 0.0}, 0.0), ({"address": 1.0}, 0.5)]

    assert LogisticRanker().fit(samples).weights == LogisticRanker().fit(samples).weights


def test_no_samples_leaves_an_untrained_even_ranker() -> None:
    ranker = LogisticRanker().fit([])

    assert ranker.predict({"address": 1.0}) == 0.5


def test_saved_ranker_predicts_the_same(tmp_path: Path) -> None:
    ranker = LogisticRanker().fit([({"address": 1.0}, 1.0), ({"address": 0.0}, 0.0)])
    path = tmp_path / "models" / "ranker.json"

    ranker.save(path)
    loaded = LogisticRanker.load(path)

    assert loaded.predict({"address": 1.0}) == ranker.predict({"address": 1.0})


@given(st.floats(min_value=-1e6, max_value=1e6), st.floats(min_value=-1e3, max_value=1e3))
def test_predictions_stay_between_zero_and_one(weight: float, value: float) -> None:
    prediction = LogisticRanker(weights={"x": weight}).predict({"x": value})

    assert 0.0 <= prediction <= 1.0
