"""The guided "add a bot" flow."""

import contextlib
import secrets
from collections.abc import Awaitable, Callable
from datetime import datetime

import httpx

from kick_commenter.kick.bots import BotAccount, BotRegistry
from kick_commenter.kick.client import KickApi
from kick_commenter.kick.errors import KickError
from kick_commenter.kick.oauth import BOT_SCOPES, OAuthClient, PkcePair
from kick_commenter.kick.token_store import TokenStore
from kick_commenter.kick.tokens import StaticTokenProvider

WaitForCode = Callable[[str], Awaitable[str]]


async def add_bot(  # noqa: PLR0913
    *,
    http: httpx.AsyncClient,
    oauth: OAuthClient,
    store: TokenStore,
    registry: BotRegistry,
    open_browser: Callable[[str], object],
    wait_for_code: WaitForCode,
    clock: Callable[[], datetime],
) -> BotAccount:
    """Log in as a bot account in the browser and save it to the bot list.

    ``wait_for_code`` receives the expected ``state`` and returns the code from
    Kick's redirect.
    """
    pkce = PkcePair.generate()
    state = secrets.token_urlsafe(24)
    open_browser(oauth.authorize_url(state, pkce, BOT_SCOPES))
    code = await wait_for_code(state)

    token = await oauth.exchange_code(code, pkce, clock())
    user = await KickApi(http, StaticTokenProvider(token.access_token)).current_user()

    bot = BotAccount(user_id=user.user_id, name=user.name, added_at=clock())
    store.save(bot.token_key, token)
    registry.add(bot)
    return bot


async def remove_bot(
    *,
    name: str,
    oauth: OAuthClient,
    store: TokenStore,
    registry: BotRegistry,
) -> BotAccount:
    """Revoke the bot's tokens at Kick, delete them locally and drop it from the list."""
    bot = registry.get(name)
    token = store.load(bot.token_key)
    if token is not None:
        for value in (token.access_token, token.refresh_token):
            # A failed revoke must not block removal; the local copy goes either way.
            if value:
                with contextlib.suppress(KickError, httpx.HTTPError):
                    await oauth.revoke(value)
    store.delete(bot.token_key)
    registry.remove(name)
    return bot
