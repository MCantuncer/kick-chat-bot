"""Application settings, read from environment variables or a local .env file."""

from pathlib import Path

from pydantic import Field, SecretStr
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

    @property
    def redirect_uri(self) -> str:
        """The callback URL registered in the Kick developer app."""
        return f"http://localhost:{self.redirect_port}/callback"

    @property
    def bots_file(self) -> Path:
        """Where the bot list is saved."""
        return self.data_dir / "bots.json"
