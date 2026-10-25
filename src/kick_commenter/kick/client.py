"""A small client for the public Kick API at ``api.kick.com``."""

from typing import Any

import httpx
from pydantic import BaseModel

from kick_commenter.kick.errors import KickAPIError, KickAuthError, KickRateLimitedError
from kick_commenter.kick.tokens import TokenProvider

API_BASE_URL = "https://api.kick.com/public/v1"
HTTP_UNAUTHORIZED = 401
HTTP_TOO_MANY_REQUESTS = 429


class KickUser(BaseModel):
    """A Kick account."""

    user_id: int
    name: str


class KickChannel(BaseModel):
    """A Kick channel and whether it is live right now."""

    broadcaster_user_id: int
    slug: str
    is_live: bool


class KickApi:
    """Calls the public Kick API with tokens from a ``TokenProvider``."""

    def __init__(self, http: httpx.AsyncClient, tokens: TokenProvider) -> None:
        """Use ``http`` for requests and ``tokens`` for authorization."""
        self._http = http
        self._tokens = tokens

    async def current_user(self) -> KickUser:
        """Return the account the token belongs to."""
        data = await self._get("/users")
        user = data[0]
        return KickUser(user_id=user["user_id"], name=user["name"])

    async def channels_by_slug(self, slugs: list[str]) -> list[KickChannel]:
        """Look up channels by their URL names, for example ``thetoxicparty``."""
        data = await self._get("/channels", params={"slug": slugs})
        return [
            KickChannel(
                broadcaster_user_id=channel["broadcaster_user_id"],
                slug=channel["slug"],
                is_live=bool((channel.get("stream") or {}).get("is_live", False)),
            )
            for channel in data
        ]

    async def _get(self, path: str, params: dict[str, list[str]] | None = None) -> Any:
        response = await self._send("GET", path, params=params)
        return response.json()["data"]

    async def _send(
        self, method: str, path: str, params: dict[str, list[str]] | None = None
    ) -> httpx.Response:
        response = await self._attempt(method, path, params, force_refresh=False)
        if response.status_code == HTTP_UNAUTHORIZED:
            response = await self._attempt(method, path, params, force_refresh=True)
        if response.status_code == HTTP_UNAUTHORIZED:
            msg = "Kick rejected the token after a refresh"
            raise KickAuthError(msg)
        if response.status_code == HTTP_TOO_MANY_REQUESTS:
            raise KickRateLimitedError(_retry_after(response))
        if response.is_error:
            raise KickAPIError(response.status_code, response.text)
        return response

    async def _attempt(
        self,
        method: str,
        path: str,
        params: dict[str, list[str]] | None,
        *,
        force_refresh: bool,
    ) -> httpx.Response:
        token = await self._tokens.access_token(force_refresh=force_refresh)
        return await self._http.request(
            method,
            f"{API_BASE_URL}{path}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None
