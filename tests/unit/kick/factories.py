from datetime import UTC, datetime, timedelta

import httpx

from kick_commenter.kick.oauth import OAuthToken

NOW = datetime(2026, 10, 25, 20, 0, tzinfo=UTC)


def make_token(
    access: str = "access-1", refresh: str | None = "refresh-1", ttl: int = 3600
) -> OAuthToken:
    return OAuthToken(
        access_token=access, refresh_token=refresh, expires_at=NOW + timedelta(seconds=ttl)
    )


def token_response(access: str = "access-2", refresh: str = "refresh-2") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "access_token": access,
            "token_type": "Bearer",
            "refresh_token": refresh,
            "expires_in": 3600,
            "scope": "user:read chat:write",
        },
    )
