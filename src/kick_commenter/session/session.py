"""Runs the bot's work until the user stops it or stops answering."""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from datetime import datetime
from enum import StrEnum
from typing import Any

from kick_commenter.session.commands import HELP_TEXT, Command, parse_command
from kick_commenter.session.idle import IdleState, IdleTimer, minutes

Clock = Callable[[], datetime]
Sleep = Callable[[float], Awaitable[None]]
Work = Callable[[asyncio.Event], Coroutine[Any, Any, object]]


class StopReason(StrEnum):
    """Why a session ended."""

    USER = "user"
    IDLE = "idle"
    FINISHED = "finished"


class Session:
    """Wraps the bot's work with an idle auto-stop and typed commands.

    The work gets an event that is set when the session should end, and must
    return soon after.
    """

    def __init__(  # noqa: PLR0913
        self,
        work: Work,
        idle: IdleTimer,
        *,
        clock: Clock,
        say: Callable[[str], None],
        status: Callable[[], str] = lambda: "running",
        tick_seconds: float = 1.0,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        """Prepare a session; nothing runs until :meth:`run`."""
        self._work = work
        self._idle = idle
        self._clock = clock
        self._say = say
        self._status = status
        self._tick = tick_seconds
        self._sleep = sleep
        self._stop = asyncio.Event()
        self._reason = StopReason.FINISHED
        self._warned = False

    async def run(self, commands: AsyncIterator[str]) -> StopReason:
        """Run until the work ends, the user types stop, or the idle timer runs out."""
        work = asyncio.create_task(self._work(self._stop))
        helpers = [
            asyncio.create_task(self._watch_idle()),
            asyncio.create_task(self._read_commands(commands)),
        ]
        stopper = asyncio.create_task(self._stop.wait())
        await asyncio.wait({work, stopper}, return_when=asyncio.FIRST_COMPLETED)
        self._stop.set()
        for task in [*helpers, stopper]:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await work
        return self._reason

    def _end(self, reason: StopReason) -> None:
        self._reason = reason
        self._stop.set()

    async def _watch_idle(self) -> None:
        while True:
            now = self._clock()
            match self._idle.state(now):
                case IdleState.EXPIRED:
                    self._say("No input for a while, so the session is stopping.")
                    self._end(StopReason.IDLE)
                    return
                case IdleState.WARNING if not self._warned:
                    left = minutes(self._idle.remaining(now))
                    self._say(
                        f"Stopping in {left} min because there has been no input. "
                        "Type 'continue' to keep going."
                    )
                    self._warned = True
                case _:
                    pass
            await self._sleep(self._tick)

    async def _read_commands(self, commands: AsyncIterator[str]) -> None:
        # If input ends (no terminal attached), the idle timer still applies.
        async for line in commands:
            if not line.strip():
                continue
            match parse_command(line):
                case Command.CONTINUE:
                    now = self._clock()
                    self._idle.touch(now)
                    self._warned = False
                    left = minutes(self._idle.remaining(now))
                    self._say(f"OK, staying on for another {left} min.")
                case Command.STATUS:
                    left = minutes(self._idle.remaining(self._clock()))
                    self._say(f"{self._status()}. Stops in {left} min without input.")
                case Command.STOP:
                    self._say("Stopping.")
                    self._end(StopReason.USER)
                    return
                case Command.HELP | None:
                    self._say(HELP_TEXT)
