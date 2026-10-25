"""Makes sure only one bot runs in a channel at a time, across processes."""

import json
import os
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Self

import psutil
from pydantic import BaseModel


class LockInfo(BaseModel):
    """Who holds a channel."""

    pid: int
    bot: str
    started_at: datetime


class ChannelBusyError(Exception):
    """Another running session already holds the channel."""

    def __init__(self, channel: str, holder: LockInfo, path: Path) -> None:
        """Describe who holds ``channel``."""
        super().__init__(
            f"{channel} already has a session running (bot {holder.bot}, process {holder.pid}). "
            f"Stop that session first. If it is not running anymore, delete {path}."
        )
        self.holder = holder


class ChannelLock:
    """A lock file per channel, released when the session ends.

    A lock left behind by a session that crashed is detected and replaced.
    """

    def __init__(self, directory: Path, channel: str, info: LockInfo) -> None:
        """Prepare to lock ``channel`` on behalf of the session described by ``info``."""
        self._channel = channel
        self._path = directory / f"{channel}.lock"
        self._info = info

    @property
    def path(self) -> Path:
        """The lock file."""
        return self._path

    def acquire(self) -> None:
        """Take the channel, or raise :class:`ChannelBusyError` if it is taken."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._try_create():
            return
        holder = self._read_holder()
        if holder is not None and _is_running(holder.pid):
            raise ChannelBusyError(self._channel, holder, self._path)
        self._path.unlink(missing_ok=True)  # stale: its session is gone
        if not self._try_create():
            holder = self._read_holder()
            raise ChannelBusyError(self._channel, holder or self._info, self._path)

    def release(self) -> None:
        """Give the channel back, if this session still holds it."""
        holder = self._read_holder()
        if holder is not None and holder.pid == self._info.pid:
            self._path.unlink(missing_ok=True)

    def __enter__(self) -> Self:
        """Acquire the lock."""
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release the lock."""
        self.release()

    def _try_create(self) -> bool:
        try:
            fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(self._info.model_dump_json())
        return True

    def _read_holder(self) -> LockInfo | None:
        try:
            return LockInfo.model_validate_json(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None


def _is_running(pid: int) -> bool:
    return pid == os.getpid() or psutil.pid_exists(pid)
