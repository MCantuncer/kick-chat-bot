import asyncio
import socket
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx

from kick_commenter.kick.bots import BotAccount, BotRegistry
from kick_commenter.kick.callback import wait_for_code
from kick_commenter.kick.errors import KickAuthError
from kick_commenter.kick.login import add_bot, remove_bot
from kick_commenter.kick.oauth import OAuthClient
from kick_commenter.kick.token_store import MemoryTokenStore

from ..unit.kick.factories import NOW, make_token, token_response


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def get(port: int, target: str) -> str:
    # Retry briefly until the callback server is listening.
    for _ in range(50):
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            break
        except OSError:
            await asyncio.sleep(0.02)
    writer.write(f"GET {target} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
    await writer.drain()
    response = (await reader.read()).decode()
    writer.close()
    return response


async def test_callback_returns_code_when_state_matches() -> None:
    port = free_port()
    waiter = asyncio.create_task(wait_for_code("127.0.0.1", port, "s1", timeout=5))

    page = await get(port, "/callback?code=abc&state=s1")

    assert await waiter == "abc"
    assert "Bot added." in page


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ("code=abc&state=forged", "wrong state"),
        ("error=access_denied&state=s1", "access_denied"),
        ("state=s1", "no code"),
    ],
)
async def test_callback_rejects_bad_redirects(query: str, message: str) -> None:
    port = free_port()
    waiter = asyncio.create_task(wait_for_code("127.0.0.1", port, "s1", timeout=5))

    page = await get(port, f"/callback?{query}")

    with pytest.raises(KickAuthError, match=message):
        await waiter
    assert "Login failed." in page


async def test_callback_ignores_other_paths_and_times_out() -> None:
    port = free_port()
    waiter = asyncio.create_task(wait_for_code("127.0.0.1", port, "s1", timeout=0.5))

    page = await get(port, "/favicon.ico")

    assert page.startswith("HTTP/1.1 404")
    with pytest.raises(KickAuthError, match="timed out"):
        await waiter


@respx.mock
async def test_add_bot_logs_in_and_saves_bot_and_token(tmp_path: Path) -> None:
    respx.post("https://id.kick.com/oauth/token").mock(return_value=token_response())
    respx.get("https://api.kick.com/public/v1/users").mock(
        return_value=httpx.Response(200, json={"data": [{"user_id": 77, "name": "golfwangtr"}]})
    )
    store = MemoryTokenStore()
    registry = BotRegistry(tmp_path / "bots.json")
    opened: list[str] = []

    async def fake_redirect(state: str) -> str:
        assert parse_qs(urlsplit(opened[0]).query)["state"] == [state]
        return "the-code"

    async with httpx.AsyncClient() as http:
        oauth = OAuthClient(http, "id", "secret", "http://localhost:8765/callback")
        bot = await add_bot(
            http=http,
            oauth=oauth,
            store=store,
            registry=registry,
            open_browser=opened.append,
            wait_for_code=fake_redirect,
            clock=lambda: NOW,
        )

    assert bot.name == "golfwangtr"
    assert registry.get("golfwangtr").user_id == 77
    saved = store.load("bot:77")
    assert saved is not None
    assert saved.access_token == "access-2"


@respx.mock
async def test_remove_bot_revokes_and_forgets_even_if_revoke_fails(tmp_path: Path) -> None:
    revoke = respx.post("https://id.kick.com/oauth/revoke").mock(
        side_effect=[httpx.Response(200), httpx.ConnectError("offline")]
    )
    store = MemoryTokenStore()
    registry = BotRegistry(tmp_path / "bots.json")
    registry.add(BotAccount(user_id=5, name="bot", added_at=NOW))
    store.save("bot:5", make_token())

    async with httpx.AsyncClient() as http:
        oauth = OAuthClient(http, "id", "secret", "http://localhost:8765/callback")
        removed = await remove_bot(name="bot", oauth=oauth, store=store, registry=registry)

    assert removed.user_id == 5
    assert revoke.call_count == 2
    assert store.load("bot:5") is None
    assert registry.all() == []
