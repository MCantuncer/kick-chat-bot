"""Word lists behind the safety filters.

Entries are lowercase. Text and entries are both compared with repeated
letters squashed to one, so "yarrrak" and "yarak" meet.
``*_STEMS`` match the start of a word, so Turkish suffixes are caught
("siktir", "sikerim"); ``*_WORDS`` match whole words only, for short
roots that start innocent words too ("göt" is listed whole so "götür" passes).

Kept deliberately small and high-precision for slurs; a candidate that trips
a filter is simply dropped, so a false alarm only costs one option.
"""

# Insults, slurs and sexual terms, Turkish and English.
ABUSE_STEMS = frozenset(
    {
        # Turkish
        "amına",
        "amina",
        "amcık",
        "amcik",
        "orospu",
        "orosbu",
        "sik",
        "yarak",
        "pezevenk",
        "kahpe",
        "şerefsiz",
        "serefsiz",
        "götveren",
        "gotveren",
        "ibne",
        "puşt",
        "pust",
        "gerizekal",
        "dalyarak",
        "porno",
        # English
        "fuck",
        "shit",
        "bitch",
        "cunt",
        "whore",
        "slut",
        "fag",
        "niger",
        "nigga",
        "retard",
        "porn",
    }
)
ABUSE_WORDS = frozenset(
    {
        "amk",
        "aq",
        "mk",
        "göt",
        "piç",
        "salak",
        "aptal",
        "dick",
        "pussy",
        "ass",
        "asshole",
        "sex",
        "seks",
    }
)

# Topics the bot stays out of: politics, religion, money, gambling and betting.
TOPIC_STEMS = frozenset(
    {
        "siyaset",
        "seçim",
        "secim",
        "erdoğan",
        "erdogan",
        "kılıçdaroğlu",
        "imamoğlu",
        "bahis",
        "kumar",
        "iddaa",
        "casino",
        "kripto",
        "bitcoin",
        "dinsiz",
        "ateist",
        "politic",
        "election",
        "trump",
        "biden",
        "religio",
        "gambl",
        "crypto",
        "betting",
    }
)
TOPIC_WORDS = frozenset({"akp", "chp", "mhp", "hdp", "kuran", "bet", "slot", "jesus"})

# Remarks about someone's looks or body.
LOOKS_STEMS = frozenset(
    {"güzelsin", "güzelmişsin", "yakışıklı", "seksi", "sexy", "çirkin", "ugly", "şişman"}
)
LOOKS_WORDS = frozenset({"hot", "cute", "fat"})
