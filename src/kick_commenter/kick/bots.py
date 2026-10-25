"""The list of bot accounts the user can pick from when starting a session.

Only names and IDs live here. Tokens are kept in the token store.
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, TypeAdapter


class BotAccount(BaseModel):
    """A Kick account the app may post as."""

    user_id: int
    name: str
    added_at: datetime

    @property
    def token_key(self) -> str:
        """Key under which this bot's token is stored."""
        return f"bot:{self.user_id}"


_BOT_LIST = TypeAdapter(list[BotAccount])


class BotRegistry:
    """Bot accounts saved as a small JSON file in the data directory."""

    def __init__(self, path: Path) -> None:
        """Read and write the bot list at ``path``."""
        self._path = path

    def all(self) -> list[BotAccount]:
        """Return all saved bots, oldest first."""
        if not self._path.exists():
            return []
        return _BOT_LIST.validate_json(self._path.read_bytes())

    def get(self, name: str) -> BotAccount:
        """Return the bot with this name (case-insensitive)."""
        for bot in self.all():
            if bot.name.casefold() == name.casefold():
                return bot
        msg = f"no bot named {name!r}"
        raise KeyError(msg)

    def add(self, bot: BotAccount) -> None:
        """Save a bot, replacing an earlier entry for the same account."""
        bots = [existing for existing in self.all() if existing.user_id != bot.user_id]
        self._write([*bots, bot])

    def remove(self, name: str) -> BotAccount:
        """Delete the bot with this name and return it."""
        bot = self.get(name)
        self._write([existing for existing in self.all() if existing.user_id != bot.user_id])
        return bot

    def _write(self, bots: list[BotAccount]) -> None:
        # Write to a temp file and rename, so a crash never leaves a half-written list.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(_BOT_LIST.dump_python(bots, mode="json"), indent=2)
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        Path(tmp).replace(self._path)
