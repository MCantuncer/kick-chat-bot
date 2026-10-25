from pathlib import Path

import pytest

from kick_commenter.kick.bots import BotAccount, BotRegistry

from .factories import NOW


def bot(user_id: int, name: str) -> BotAccount:
    return BotAccount(user_id=user_id, name=name, added_at=NOW)


def test_registry_is_empty_before_anything_is_added(tmp_path: Path) -> None:
    assert BotRegistry(tmp_path / "bots.json").all() == []


def test_added_bots_persist_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "bots.json"
    BotRegistry(path).add(bot(1, "golfwangtr"))
    BotRegistry(path).add(bot(2, "second"))

    assert [b.name for b in BotRegistry(path).all()] == ["golfwangtr", "second"]


def test_adding_same_account_replaces_entry(tmp_path: Path) -> None:
    registry = BotRegistry(tmp_path / "bots.json")
    registry.add(bot(1, "old-name"))
    registry.add(bot(1, "new-name"))

    assert [b.name for b in registry.all()] == ["new-name"]


def test_get_matches_name_ignoring_case(tmp_path: Path) -> None:
    registry = BotRegistry(tmp_path / "bots.json")
    registry.add(bot(1, "GolfWangTR"))

    assert registry.get("golfwangtr").user_id == 1


def test_remove_deletes_bot_and_returns_it(tmp_path: Path) -> None:
    registry = BotRegistry(tmp_path / "bots.json")
    registry.add(bot(1, "a"))
    registry.add(bot(2, "b"))

    removed = registry.remove("a")

    assert removed.user_id == 1
    assert [b.name for b in registry.all()] == ["b"]


def test_get_raises_for_unknown_name(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="no bot named"):
        BotRegistry(tmp_path / "bots.json").get("ghost")


def test_bot_list_file_holds_no_tokens(tmp_path: Path) -> None:
    path = tmp_path / "bots.json"
    BotRegistry(path).add(bot(1, "a"))

    assert "token" not in path.read_text()
    assert bot(1, "a").token_key == "bot:1"
