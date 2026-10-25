from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from kick_commenter import __version__
from kick_commenter.cli import app
from kick_commenter.kick.bots import BotAccount, BotRegistry

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
