"""A one-shot local web server that receives Kick's login redirect."""

import asyncio
import secrets
from urllib.parse import parse_qs, urlsplit

from kick_commenter.kick.errors import KickAuthError

_PAGE = (
    "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n"
    "<html><body><h3>{message}</h3><p>You can close this tab.</p></body></html>"
)


async def wait_for_code(host: str, port: int, expected_state: str, timeout: float) -> str:
    """Wait for the redirect to ``/callback`` and return the authorization code.

    Raises ``KickAuthError`` when Kick reports an error, the ``state`` does not
    match (a possible forged request), or nothing arrives within ``timeout`` seconds.
    """
    result: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request_line = (await reader.readline()).decode("latin-1")
        parts = request_line.split(" ")
        target = parts[1] if len(parts) > 1 else ""
        url = urlsplit(target)
        if url.path != "/callback":
            writer.write(b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n")
        else:
            outcome = _read_callback(parse_qs(url.query), expected_state)
            message = "Bot added." if isinstance(outcome, str) else "Login failed."
            writer.write(_PAGE.format(message=message).encode("utf-8"))
            if not result.done():
                if isinstance(outcome, str):
                    result.set_result(outcome)
                else:
                    result.set_exception(outcome)
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, host, port)
    try:
        async with asyncio.timeout(timeout):
            return await result
    except TimeoutError:
        msg = "timed out waiting for the Kick login"
        raise KickAuthError(msg) from None
    finally:
        server.close()
        await server.wait_closed()


def _read_callback(query: dict[str, list[str]], expected_state: str) -> str | KickAuthError:
    if "error" in query:
        return KickAuthError(f"Kick login failed: {query['error'][0]}")
    if not secrets.compare_digest(query.get("state", [""])[0], expected_state):
        return KickAuthError("login response had the wrong state; ignoring it")
    code = query.get("code", [""])[0]
    if not code:
        return KickAuthError("login response had no code")
    return code
