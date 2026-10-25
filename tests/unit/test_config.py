from pathlib import Path

import pytest
from pydantic import ValidationError

from kick_commenter.config import Settings


def test_settings_use_safe_defaults_when_nothing_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(Path(__file__).parent)

    settings = Settings()

    assert settings.idle_timeout_minutes == 120
    assert settings.dry_run is True


def test_settings_read_environment_when_prefixed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KICK_COMMENTER_IDLE_TIMEOUT_MINUTES", "30")
    monkeypatch.setenv("KICK_COMMENTER_DRY_RUN", "false")

    settings = Settings()

    assert settings.idle_timeout_minutes == 30
    assert settings.dry_run is False


def test_settings_reject_timeout_when_not_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KICK_COMMENTER_IDLE_TIMEOUT_MINUTES", "0")

    with pytest.raises(ValidationError):
        Settings()
