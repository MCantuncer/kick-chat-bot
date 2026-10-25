import pytest

from kick_commenter.session.commands import Command, parse_command


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("continue\n", Command.CONTINUE),
        ("  CONTINUE ", Command.CONTINUE),
        ("c", Command.CONTINUE),
        ("status", Command.STATUS),
        ("s", Command.STATUS),
        ("stop", Command.STOP),
        ("quit", Command.STOP),
        ("exit", Command.STOP),
        ("q", Command.STOP),
        ("help", Command.HELP),
        ("?", Command.HELP),
        ("selam", None),
        ("", None),
    ],
)
def test_parse_command(line: str, expected: Command | None) -> None:
    assert parse_command(line) == expected
