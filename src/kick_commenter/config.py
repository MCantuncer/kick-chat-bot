"""Application settings, read from environment variables or a local .env file."""

from pathlib import Path
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Every field can be set as ``KICK_COMMENTER_<NAME>``."""

    model_config = SettingsConfigDict(
        env_prefix="KICK_COMMENTER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path.home() / ".kick-commenter"
    idle_timeout_minutes: int = Field(default=120, gt=0)
    idle_warning_minutes: int = Field(default=5, gt=0)
    dry_run: bool = True

    client_id: str | None = None
    client_secret: SecretStr | None = None
    redirect_port: int = Field(default=8765, gt=0, lt=65536)
    login_timeout_seconds: float = Field(default=300, gt=0)

    # Only needed if Kick rotates the public chat stream key and the lookup breaks.
    pusher_app_key: str | None = None
    pusher_cluster: str = "us2"

    @model_validator(mode="after")
    def _warning_before_timeout(self) -> Self:
        if self.idle_warning_minutes >= self.idle_timeout_minutes:
            msg = "idle_warning_minutes must be smaller than idle_timeout_minutes"
            raise ValueError(msg)
        return self

    @property
    def redirect_uri(self) -> str:
        """The callback URL registered in the Kick developer app."""
        return f"http://localhost:{self.redirect_port}/callback"

    @property
    def bots_file(self) -> Path:
        """Where the bot list is saved."""
        return self.data_dir / "bots.json"

    @property
    def chat_db(self) -> Path:
        """Where collected chat is stored."""
        return self.data_dir / "chat.sqlite3"

    @property
    def channels_file(self) -> Path:
        """Where resolved channel ids are cached."""
        return self.data_dir / "channels.json"

    @property
    def locks_dir(self) -> Path:
        """Where running sessions mark the channels they hold."""
        return self.data_dir / "locks"

    @property
    def profiles_dir(self) -> Path:
        """Where community profiles are saved, one file per channel."""
        return self.data_dir / "profiles"
