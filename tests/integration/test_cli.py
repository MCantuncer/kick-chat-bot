from typer.testing import CliRunner

from kick_commenter import __version__
from kick_commenter.cli import app

runner = CliRunner()


def test_version_prints_installed_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.output.strip() == __version__


def test_settings_lists_active_settings() -> None:
    result = runner.invoke(app, ["settings"])

    assert result.exit_code == 0
    assert "idle_timeout_minutes = 120" in result.output
