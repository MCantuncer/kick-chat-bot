import io

from kick_commenter.session.terminal import typed_lines


async def test_typed_lines_yields_each_line_until_input_closes() -> None:
    lines = [line async for line in typed_lines(io.StringIO("continue\nstop\n"))]

    assert lines == ["continue\n", "stop\n"]
