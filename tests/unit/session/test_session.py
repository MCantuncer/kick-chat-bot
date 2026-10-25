import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from kick_commenter.session.idle import IdleTimer
from kick_commenter.session.session import Session, StopReason

START = datetime(2026, 10, 25, 20, 0, tzinfo=UTC)
TICK = 60.0


class FakeClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
        await asyncio.sleep(0)


class Typed:
    """Commands the test feeds in, as if typed into the terminal."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[str | None] = asyncio.Queue()

    def type(self, line: str) -> None:
        self.queue.put_nowait(line)

    def close(self) -> None:
        self.queue.put_nowait(None)

    async def __aiter__(self) -> AsyncIterator[str]:
        while (line := await self.queue.get()) is not None:
            yield line


class Harness:
    def __init__(self, timeout_minutes: int = 10, warning_minutes: int = 2) -> None:
        self.clock = FakeClock()
        self.said: list[str] = []
        self.said_at: dict[str, datetime] = {}
        self.keep_going = False  # type "continue" when the warning shows
        self.work_saw_stop = False
        self.typed = Typed()
        self.session = Session(
            self.work,
            IdleTimer(
                timeout=timedelta(minutes=timeout_minutes),
                warning=timedelta(minutes=warning_minutes),
                last_input=START,
            ),
            clock=self.clock,
            say=self.say,
            status=lambda: "Listening",
            tick_seconds=TICK,
            sleep=self.clock.sleep,
        )

    def say(self, line: str) -> None:
        self.said.append(line)
        self.said_at[line] = self.clock.now
        if line.startswith("Stopping in") and self.keep_going:
            self.keep_going = False
            self.typed.type("continue")

    async def work(self, stop: asyncio.Event) -> None:
        await stop.wait()
        self.work_saw_stop = True

    async def run(self) -> StopReason:
        return await asyncio.wait_for(self.session.run(aiter(self.typed)), timeout=2)


async def test_session_stops_by_itself_after_the_idle_timeout_and_warns_once() -> None:
    harness = Harness()

    reason = await harness.run()

    assert reason == StopReason.IDLE
    assert harness.work_saw_stop
    assert harness.clock.now == START + timedelta(minutes=10)
    warnings = [line for line in harness.said if line.startswith("Stopping in")]
    assert warnings == [
        "Stopping in 2 min because there has been no input. Type 'continue' to keep going."
    ]
    assert harness.said[-1] == "No input for a while, so the session is stopping."


async def test_continue_restarts_the_countdown_and_rearms_the_warning() -> None:
    harness = Harness()
    harness.keep_going = True

    reason = await harness.run()

    assert reason == StopReason.IDLE
    acknowledged = harness.said_at["OK, staying on for another 10 min."]
    assert acknowledged > START + timedelta(minutes=8)
    assert harness.clock.now == acknowledged + timedelta(minutes=10)
    assert sum(line.startswith("Stopping in") for line in harness.said) == 2


async def test_stop_command_ends_the_session() -> None:
    harness = Harness()
    harness.typed.type("status")
    harness.typed.type("dance")
    harness.typed.type("")
    harness.typed.type("stop")

    reason = await harness.run()

    assert reason == StopReason.USER
    assert harness.work_saw_stop
    assert harness.said[0].startswith("Listening. Stops in ")
    assert harness.said[1].startswith("Commands:")
    assert harness.said[2] == "Stopping."


async def test_closed_input_leaves_the_idle_timer_in_charge() -> None:
    harness = Harness()
    harness.typed.close()

    assert await harness.run() == StopReason.IDLE


async def test_session_ends_when_the_work_finishes() -> None:
    harness = Harness()

    async def short_work(_stop: asyncio.Event) -> None:
        return None

    session = Session(
        short_work,
        IdleTimer(timeout=timedelta(minutes=10), warning=timedelta(minutes=1), last_input=START),
        clock=harness.clock,
        say=harness.said.append,
        sleep=harness.clock.sleep,
    )

    assert (
        await asyncio.wait_for(session.run(aiter(harness.typed)), timeout=2) == StopReason.FINISHED
    )
