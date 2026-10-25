"""Token providers that hand out a valid access token, refreshing when needed."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from kick_commenter.kick.errors import KickAuthError
from kick_commenter.kick.oauth import OAuthClient, OAuthToken
from kick_commenter.kick.token_store import TokenStore


class TokenProvider(Protocol):
    """Gives out an access token for API calls."""

    async def access_token(self, *, force_refresh: bool = False) -> str:
        """Return a usable access token, refreshing it first when asked or expired."""
        ...


class UserTokenProvider:
    """Access token for one bot account, kept in a token store and refreshed on demand."""

    def __init__(
        self,
        key: str,
        store: TokenStore,
        oauth: OAuthClient,
        clock: Callable[[], datetime],
    ) -> None:
        """Serve the token stored under ``key``."""
        self._key = key
        self._store = store
        self._oauth = oauth
        self._clock = clock

    async def access_token(self, *, force_refresh: bool = False) -> str:
        """Return a usable access token, refreshing it first when asked or expired."""
        token = self._store.load(self._key)
        if token is None:
            msg = f"no token stored for {self._key}; add the bot again"
            raise KickAuthError(msg)
        if force_refresh or token.is_expired(self._clock()):
            if token.refresh_token is None:
                msg = f"token for {self._key} expired and cannot be refreshed"
                raise KickAuthError(msg)
            token = await self._oauth.refresh(token.refresh_token, self._clock())
            self._store.save(self._key, token)
        return token.access_token


class AppTokenProvider:
    """App access token (no user), cached in memory until it expires."""

    def __init__(self, oauth: OAuthClient, clock: Callable[[], datetime]) -> None:
        """Fetch app tokens with the given OAuth client."""
        self._oauth = oauth
        self._clock = clock
        self._token: OAuthToken | None = None

    async def access_token(self, *, force_refresh: bool = False) -> str:
        """Return a usable access token, fetching a new one when asked or expired."""
        if force_refresh or self._token is None or self._token.is_expired(self._clock()):
            self._token = await self._oauth.app_token(self._clock())
        return self._token.access_token


class StaticTokenProvider:
    """A fixed token, used right after login before the token is stored."""

    def __init__(self, token: str) -> None:
        """Hand out ``token`` on every call."""
        self._token = token

    async def access_token(self, *, force_refresh: bool = False) -> str:  # noqa: ARG002
        """Return the fixed token."""
        return self._token
