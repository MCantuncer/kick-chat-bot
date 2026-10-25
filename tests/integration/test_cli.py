from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from kick_commenter import __version__, cli
from kick_commenter.cli import app
from kick_commenter.collector.lookup import ChannelIds, ChannelLookup
from kick_commenter.kick.bots import BotAccount, BotRegistry
from kick_commenter.models import ChatMessage
from kick_commenter.storage.chat_store import ChatStore

from ..unit.kick.factories import NOW

runner = CliRunner()


def test_version_prints_installed_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.output.strip() == __version__


def test_settings_lists_active_settings() -> None:
    result = runner.invoke(app, ["settings"])

    assert result.exit_code == 0
    assert "idle_timeout_minutes = 120" in result.output


def test_bots_list_explains_how_to_add_when_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KICK_COMMENTER_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["bots", "list"])

    assert result.exit_code == 0
    assert "bots add" in result.output


def test_bots_list_shows_saved_bots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KICK_COMMENTER_DATA_DIR", str(tmp_path))
    BotRegistry(tmp_path / "bots.json").add(BotAccount(user_id=7, name="golfwangtr", added_at=NOW))

    result = runner.invoke(app, ["bots", "list"])

    assert "golfwangtr (id 7, added 2026-10-25)" in result.output


def test_kick_commands_ask_for_app_credentials_when_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("KICK_COMMENTER_CLIENT_ID", raising=False)

    result = runner.invoke(app, ["channel", "thetoxicparty"])

    assert result.exit_code == 1
    assert "KICK_COMMENTER_CLIENT_ID" in result.output


@pytest.fixture
def credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("KICK_COMMENTER_CLIENT_ID", "id")
    monkeypatch.setenv("KICK_COMMENTER_CLIENT_SECRET", "secret")
    monkeypatch.setenv("KICK_COMMENTER_DATA_DIR", str(tmp_path))
    return tmp_path


@respx.mock
@pytest.mark.usefixtures("credentials")
def test_channel_prints_id_and_live_state() -> None:
    respx.post("https://id.kick.com/oauth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "app", "expires_in": 3600})
    )
    respx.get("https://api.kick.com/public/v1/channels").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"broadcaster_user_id": 9, "slug": "thetoxicparty", "stream": None}]},
        )
    )

    result = runner.invoke(app, ["channel", "thetoxicparty"])

    assert result.exit_code == 0
    assert "thetoxicparty: broadcaster id 9, offline" in result.output


@respx.mock
@pytest.mark.usefixtures("credentials")
def test_channel_reports_unknown_channel() -> None:
    respx.post("https://id.kick.com/oauth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "app", "expires_in": 3600})
    )
    respx.get("https://api.kick.com/public/v1/channels").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    result = runner.invoke(app, ["channel", "ghost"])

    assert result.exit_code == 1
    assert "No channel named 'ghost'" in result.output


@respx.mock
@pytest.mark.usefixtures("credentials")
def test_kick_errors_are_reported_without_traceback() -> None:
    respx.post("https://id.kick.com/oauth/token").mock(return_value=httpx.Response(400))

    result = runner.invoke(app, ["channel", "thetoxicparty"])

    assert result.exit_code == 1
    assert "Kick error" in result.output


@pytest.mark.usefixtures("credentials")
def test_bots_remove_reports_unknown_bot() -> None:
    result = runner.invoke(app, ["bots", "remove", "ghost"])

    assert result.exit_code == 1
    assert "No bot named 'ghost'" in result.output


@respx.mock
def test_collect_explains_unknown_channel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KICK_COMMENTER_DATA_DIR", str(tmp_path))
    respx.get("https://kick.com/api/v2/channels/ghost").mock(return_value=httpx.Response(404))

    result = runner.invoke(app, ["collect", "ghost"])

    assert result.exit_code == 1
    assert "no channel named" in result.output


def test_collect_saves_chat_until_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, chat_message: ChatMessage
) -> None:
    monkeypatch.setenv("KICK_COMMENTER_DATA_DIR", str(tmp_path))

    class OneMessageSource:
        def __init__(self, chatroom_id: int, channel_id: int, **_: object) -> None:
            assert (chatroom_id, channel_id) == (1001, 2002)

        async def stream(self) -> AsyncIterator[ChatMessage]:
            yield chat_message
            raise KeyboardInterrupt

    monkeypatch.setattr(cli, "PusherChatSource", OneMessageSource)

    result = runner.invoke(
        app, ["collect", "TheToxicParty", "--chatroom-id", "1001", "--channel-id", "2002"]
    )

    assert result.exit_code == 0
    assert "viewer: reis bugün başka" in result.output
    assert "Saved 1 messages and 0 events" in result.output
    assert "thetoxicparty" in (tmp_path / "channels.json").read_text()


@pytest.mark.parametrize(
    ("env_key", "expected_url"),
    [
        (None, "wss://ws-eu.pusher.com/app/fromkick?"),
        ("override", "wss://ws-us2.pusher.com/app/override?"),
    ],
)
@respx.mock
def test_collect_connects_to_the_current_stream_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env_key: str | None, expected_url: str
) -> None:
    monkeypatch.setenv("KICK_COMMENTER_DATA_DIR", str(tmp_path))
    if env_key:
        monkeypatch.setenv("KICK_COMMENTER_PUSHER_APP_KEY", env_key)
    respx.post("https://web.kick.com/api/v1/realtime/channels/2002/chat/connection").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "connections": [
                        {
                            "provider": "pusher",
                            "credentials": {"app_key": "fromkick", "cluster": "eu"},
                        }
                    ]
                }
            },
        )
    )
    urls: list[str] = []

    class RecordingSource:
        def __init__(self, *_: int, endpoint: Callable[[], Awaitable[str]]) -> None:
            self._endpoint = endpoint

        async def stream(self) -> AsyncIterator[ChatMessage]:
            urls.append(await self._endpoint())
            raise KeyboardInterrupt
            yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(cli, "PusherChatSource", RecordingSource)

    result = runner.invoke(
        app, ["collect", "thetoxicparty", "--chatroom-id", "1", "--channel-id", "2002"]
    )

    assert result.exit_code == 0, result.output
    assert urls[0].startswith(expected_url)


def test_languages_needs_collected_chat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KICK_COMMENTER_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["languages", "thetoxicparty"])

    assert result.exit_code == 1
    assert "collect thetoxicparty" in result.output


def test_languages_reports_the_channel_mix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, chat_message: ChatMessage
) -> None:
    monkeypatch.setenv("KICK_COMMENTER_DATA_DIR", str(tmp_path))
    ChannelLookup(httpx.AsyncClient(), tmp_path / "channels.json").remember(
        ChannelIds(slug="thetoxicparty", channel_id=chat_message.channel_id, chatroom_id=1)
    )
    store = ChatStore(tmp_path / "chat.sqlite3")
    texts = ["helal olsun reis bugün çok iyi oynadın"] * 30 + ["gg"] * 5
    for n, text in enumerate(texts):
        store.save_message(chat_message.model_copy(update={"message_id": str(n), "text": text}))
    store.close()

    result = runner.invoke(app, ["languages", "@TheToxicParty"])

    assert result.exit_code == 0, result.output
    assert "thetoxicparty: 35 messages. Languages: tr 100%." in result.output
    assert "5 messages were too short to tell." in result.output
    assert "Main language: tr" in result.output


def test_languages_with_only_short_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, chat_message: ChatMessage
) -> None:
    monkeypatch.setenv("KICK_COMMENTER_DATA_DIR", str(tmp_path))
    ChannelLookup(httpx.AsyncClient(), tmp_path / "channels.json").remember(
        ChannelIds(slug="quiet", channel_id=chat_message.channel_id, chatroom_id=1)
    )
    store = ChatStore(tmp_path / "chat.sqlite3")
    store.save_message(chat_message.model_copy(update={"text": "gg"}))
    store.close()

    result = runner.invoke(app, ["languages", "quiet"])

    assert result.exit_code == 0
    assert "Not enough saved chat for quiet yet (1 messages)." in result.output


def test_profile_learns_from_saved_chat_and_saves_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, chat_message: ChatMessage
) -> None:
    monkeypatch.setenv("KICK_COMMENTER_DATA_DIR", str(tmp_path))
    ChannelLookup(httpx.AsyncClient(), tmp_path / "channels.json").remember(
        ChannelIds(slug="thetoxicparty", channel_id=chat_message.channel_id, chatroom_id=1)
    )
    store = ChatStore(tmp_path / "chat.sqlite3")
    lines = (Path(__file__).parent.parent / "fixtures" / "community_chat.txt").read_text(
        encoding="utf-8"
    )
    for n, text in enumerate(lines.splitlines()):
        store.save_message(chat_message.model_copy(update={"message_id": str(n), "text": text}))
    store.close()

    result = runner.invoke(app, ["profile", "thetoxicparty"])

    assert result.exit_code == 0, result.output
    assert "thetoxicparty: learned from 240 messages." in result.output
    assert "Main language: tr" in result.output
    assert "How they address people: reis, kral, abi" in result.output
    assert "Favorite emotes: KEKW, LUL" in result.output
    assert (tmp_path / "profiles" / "thetoxicparty.json").exists()


def test_profile_with_no_chat_yet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KICK_COMMENTER_DATA_DIR", str(tmp_path))
    ChannelLookup(httpx.AsyncClient(), tmp_path / "channels.json").remember(
        ChannelIds(slug="quiet", channel_id=5, chatroom_id=1)
    )

    result = runner.invoke(app, ["profile", "quiet"])

    assert result.exit_code == 0, result.output
    assert "learned from 0 messages" in result.output
    assert "Their words: (not enough chat yet)" in result.output
    assert "Favorite emotes: (none yet)" in result.output


def save_chat(tmp_path: Path, chat_message: ChatMessage, slug: str, texts: list[str]) -> None:
    ChannelLookup(httpx.AsyncClient(), tmp_path / "channels.json").remember(
        ChannelIds(slug=slug, channel_id=chat_message.channel_id, chatroom_id=1)
    )
    store = ChatStore(tmp_path / "chat.sqlite3")
    for n, text in enumerate(texts):
        sent_at = chat_message.sent_at + timedelta(seconds=3 * n)
        store.save_message(
            chat_message.model_copy(update={"message_id": str(n), "text": text, "sent_at": sent_at})
        )
    store.close()


def test_warmup_reports_a_settled_channel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, chat_message: ChatMessage
) -> None:
    monkeypatch.setenv("KICK_COMMENTER_DATA_DIR", str(tmp_path))
    save_chat(tmp_path, chat_message, "thetoxicparty", ["helal olsun reis", "aynen kral"] * 300)

    result = runner.invoke(app, ["warmup", "thetoxicparty"])

    assert result.exit_code == 0, result.output
    assert "thetoxicparty: 600/500 messages, 28/10 min listened" in result.output
    assert "Warm-up done" in result.output


def test_warmup_reports_progress_while_still_listening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, chat_message: ChatMessage
) -> None:
    monkeypatch.setenv("KICK_COMMENTER_DATA_DIR", str(tmp_path))
    save_chat(tmp_path, chat_message, "quiet", ["helal olsun reis"] * 50)

    result = runner.invoke(app, ["warmup", "quiet"])

    assert result.exit_code == 0, result.output
    assert (
        "quiet: 50/500 messages, 2/10 min listened, 0/3 calm stretches in a row." in result.output
    )
    assert "Still warming up" in result.output


def test_warmup_needs_collected_chat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KICK_COMMENTER_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["warmup", "ghost"])

    assert result.exit_code == 1
    assert "collect ghost" in result.output
