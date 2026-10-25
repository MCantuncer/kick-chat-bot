import pytest
import respx

from kick_commenter.kick.errors import KickAuthError
from kick_commenter.kick.oauth import OAuthClient
from kick_commenter.kick.token_store import MemoryTokenStore
from kick_commenter.kick.tokens import AppTokenProvider, StaticTokenProvider, UserTokenProvider

from .factories import NOW, make_token, token_response

TOKEN_URL = "https://id.kick.com/oauth/token"


def provider(store: MemoryTokenStore, oauth: OAuthClient) -> UserTokenProvider:
    return UserTokenProvider("bot:1", store, oauth, lambda: NOW)


@respx.mock
async def test_user_token_is_reused_when_still_valid(oauth: OAuthClient) -> None:
    route = respx.post(TOKEN_URL)
    store = MemoryTokenStore()
    store.save("bot:1", make_token())

    assert await provider(store, oauth).access_token() == "access-1"
    assert not route.called


@respx.mock
async def test_user_token_is_refreshed_and_saved_when_expired(oauth: OAuthClient) -> None:
    respx.post(TOKEN_URL).mock(return_value=token_response())
    store = MemoryTokenStore()
    store.save("bot:1", make_token(ttl=10))

    assert await provider(store, oauth).access_token() == "access-2"
    saved = store.load("bot:1")
    assert saved is not None
    assert saved.refresh_token == "refresh-2"


@respx.mock
async def test_user_token_is_refreshed_when_forced(oauth: OAuthClient) -> None:
    respx.post(TOKEN_URL).mock(return_value=token_response())
    store = MemoryTokenStore()
    store.save("bot:1", make_token())

    assert await provider(store, oauth).access_token(force_refresh=True) == "access-2"


async def test_user_token_raises_when_nothing_stored(oauth: OAuthClient) -> None:
    with pytest.raises(KickAuthError, match="add the bot again"):
        await provider(MemoryTokenStore(), oauth).access_token()


async def test_user_token_raises_when_expired_without_refresh_token(oauth: OAuthClient) -> None:
    store = MemoryTokenStore()
    store.save("bot:1", make_token(refresh=None, ttl=0))

    with pytest.raises(KickAuthError, match="cannot be refreshed"):
        await provider(store, oauth).access_token()


@respx.mock
async def test_app_token_is_cached_until_forced(oauth: OAuthClient) -> None:
    route = respx.post(TOKEN_URL).mock(return_value=token_response(access="app"))
    tokens = AppTokenProvider(oauth, lambda: NOW)

    assert await tokens.access_token() == "app"
    assert await tokens.access_token() == "app"
    assert route.call_count == 1
    await tokens.access_token(force_refresh=True)
    assert route.call_count == 2


async def test_static_token_is_returned_as_is() -> None:
    assert await StaticTokenProvider("fixed").access_token(force_refresh=True) == "fixed"
