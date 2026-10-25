"""Commands the user can type into a running session."""

from enum import StrEnum


class Command(StrEnum):
    """What the user asked the running session to do."""

    CONTINUE = "continue"
    STATUS = "status"
    STOP = "stop"
    HELP = "help"


_ALIASES = {
    "c": Command.CONTINUE,
    "s": Command.STATUS,
    "q": Command.STOP,
    "quit": Command.STOP,
    "exit": Command.STOP,
    "?": Command.HELP,
}

HELP_TEXT = (
    "Commands: 'continue' keeps the session running, 'status' shows what it is doing, "
    "'stop' ends it."
)


def parse_command(line: str) -> Command | None:
    """Return the command typed on ``line``, or ``None`` if it is not one."""
    word = line.strip().casefold()
    if word in _ALIASES:
        return _ALIASES[word]
    try:
        return Command(word)
    except ValueError:
        return None
