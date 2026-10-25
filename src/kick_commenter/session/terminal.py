"""Reads the user's typed commands without blocking the event loop."""

import asyncio
import contextlib
import sys
import threading
from collections.abc import AsyncIterator
from typing import TextIO


async def typed_lines(stream: TextIO | None = None) -> AsyncIterator[str]:
    """Yield lines typed into ``stream`` (standard input by default) until it closes."""
    source = stream or sys.stdin
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def pump() -> None:
        # A blocking read in a daemon thread: it dies with the process.
        with contextlib.suppress(RuntimeError):  # the loop may be gone at exit
            for line in source:
                loop.call_soon_threadsafe(queue.put_nowait, line)
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=pump, name="typed-lines", daemon=True).start()
    while (line := await queue.get()) is not None:
        yield line
