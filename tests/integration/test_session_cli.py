import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kick_commenter import cli
from kick_commenter.cli import app
from kick_commenter.kick.bots import BotAccount, BotRegistry
from kick_commenter.kick.token_store import MemoryTokenStore
from kick_commenter.models import ChatMessage
from kick_commenter.session.lock import ChannelLock, LockInfo

from ..unit.kick.factories import NOW, make_token

runner = CliRunner()
IDS = ["--chatroom-id", "1001", "--channel-id", "2002"]


@pytest.fixture
def tokens(monkeypatch: pytest.MonkeyPatch) -> MemoryTokenStore:
    store = MemoryTokenStore()
    monkeypatch.setattr(cli, "KeyringTokenStore", lambda: store)
    return store


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("KICK_COMMENTER_DATA_DIR", str(tmp_path))
    return tmp_path


def add_bots(data_dir: Path, tokens: MemoryTokenStore, *names: str) -> list[BotAccount]:
    registry = BotRegistry(data_dir / "bots.json")
    bots = [BotAccount(user_id=i, name=name, added_at=NOW) for i, name in enumerate(names, 1)]
    for bot in bots:
        registry.add(bot)
        tokens.save(bot.token_key, make_token())
    return bots


@pytest.fixture
def chat(monkeypatch: pytest.MonkeyPatch, chat_message: ChatMessage) -> None:
    class OneMessageThenQuiet:
        def __init__(self, chatroom_id: int, channel_id: int, **_: object) -> None:
            assert (chatroom_id, channel_id) == (1001, 2002)

        async def stream(self) -> AsyncIterator[ChatMessage]:
            yield chat_message
            await asyncio.Event().wait()

    monkeypatch.setattr(cli, "PusherChatSource", OneMessageThenQuiet)


@pytest.mark.usefixtures("chat")
def test_start_runs_until_stop_and_frees_the_channel(
    data_dir: Path, tokens: MemoryTokenStore
) -> None:
    add_bots(data_dir, tokens, "golfwangtr")

    result = runner.invoke(app, ["start", "thetoxicparty", *IDS], input="continue\nstop\n")

    assert result.exit_code == 0, result.output
    assert "Session started in thetoxicparty as golfwangtr" in result.output
    assert "nothing is posted" in result.output
    assert "OK, staying on for another 120 min." in result.output
    assert "Session ended." in result.output
    assert not (data_dir / "locks" / "thetoxicparty.lock").exists()


@pytest.mark.usefixtures("chat")
def test_start_uses_the_chosen_bot_and_idle_override(
    data_dir: Path, tokens: MemoryTokenStore
) -> None:
    add_bots(data_dir, tokens, "first", "second")

    result = runner.invoke(
        app,
        ["start", "thetoxicparty", "--bot", "SECOND", "--idle-minutes", "30", *IDS],
        input="status\nstop\n",
    )

    assert result.exit_code == 0, result.output
    assert "as second" in result.output
    assert "after 30 min without input" in result.output
    assert "Listening in thetoxicparty as second." in result.output


@pytest.mark.usefixtures("tokens", "data_dir")
def test_start_without_bots_explains_how_to_add_one() -> None:
    result = runner.invoke(app, ["start", "thetoxicparty"])

    assert result.exit_code == 1
    assert "bots add" in result.output


def test_start_asks_to_pick_when_there_are_several_bots(
    data_dir: Path, tokens: MemoryTokenStore
) -> None:
    add_bots(data_dir, tokens, "first", "second")

    result = runner.invoke(app, ["start", "thetoxicparty"])

    assert result.exit_code == 1
    assert "Pick a bot with --bot. Saved bots: first, second" in result.output


def test_start_rejects_unknown_bot(data_dir: Path, tokens: MemoryTokenStore) -> None:
    add_bots(data_dir, tokens, "first")

    result = runner.invoke(app, ["start", "thetoxicparty", "--bot", "ghost"])

    assert result.exit_code == 1
    assert "No bot named 'ghost'" in result.output


def test_start_needs_a_saved_login(data_dir: Path, tokens: MemoryTokenStore) -> None:
    (bot,) = add_bots(data_dir, tokens, "first")
    tokens.delete(bot.token_key)

    result = runner.invoke(app, ["start", "thetoxicparty"])

    assert result.exit_code == 1
    assert "No saved login for first" in result.output


def test_start_refuses_a_channel_another_session_holds(
    data_dir: Path, tokens: MemoryTokenStore
) -> None:
    add_bots(data_dir, tokens, "second")
    holder = LockInfo(pid=os.getppid(), bot="first", started_at=datetime.now(UTC))
    ChannelLock(data_dir / "locks", "thetoxicparty", holder).acquire()

    result = runner.invoke(app, ["start", "@TheToxicParty", *IDS])

    assert result.exit_code == 1
    assert "already has a session running (bot first" in result.output
