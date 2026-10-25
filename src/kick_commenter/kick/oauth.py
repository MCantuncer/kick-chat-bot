"""OAuth 2.1 with PKCE against ``id.kick.com``."""

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel

from kick_commenter.kick.errors import KickAPIError, KickAuthError

AUTH_BASE_URL = "https://id.kick.com"
BOT_SCOPES = ("user:read", "channel:read", "chat:write", "events:subscribe")

# Refresh a little before expiry so a request never races the deadline.
EXPIRY_MARGIN = timedelta(seconds=60)


class OAuthToken(BaseModel):
    """An access token, with its refresh token when Kick issued one."""

    access_token: str
    refresh_token: str | None = None
    expires_at: datetime
    scope: str = ""

    def is_expired(self, now: datetime) -> bool:
        """Return whether the token should be refreshed before use."""
        return now >= self.expires_at - EXPIRY_MARGIN


class PkcePair(BaseModel):
    """A PKCE verifier and its S256 challenge."""

    verifier: str
    challenge: str

    @classmethod
    def generate(cls) -> "PkcePair":
        """Create a fresh random verifier and its challenge."""
        verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return cls(verifier=verifier, challenge=challenge)


class OAuthClient:
    """Talks to Kick's OAuth server for one developer app."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> None:
        """Create a client for the given app credentials."""
        self._http = http
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    def authorize_url(self, state: str, pkce: PkcePair, scopes: tuple[str, ...]) -> str:
        """Build the URL the user opens to approve the app."""
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "scope": " ".join(scopes),
                "code_challenge": pkce.challenge,
                "code_challenge_method": "S256",
                "state": state,
            }
        )
        return f"{AUTH_BASE_URL}/oauth/authorize?{query}"

    async def exchange_code(self, code: str, pkce: PkcePair, now: datetime) -> OAuthToken:
        """Exchange an authorization code for a user token."""
        return await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._redirect_uri,
                "code_verifier": pkce.verifier,
            },
            now,
        )

    async def refresh(self, refresh_token: str, now: datetime) -> OAuthToken:
        """Get a new user token. Kick rotates the refresh token too."""
        return await self._token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}, now
        )

    async def app_token(self, now: datetime) -> OAuthToken:
        """Get an app access token (client credentials, no user)."""
        return await self._token_request({"grant_type": "client_credentials"}, now)

    async def revoke(self, token: str) -> None:
        """Revoke a token at Kick."""
        response = await self._http.post(
            f"{AUTH_BASE_URL}/oauth/revoke",
            params={"token": token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.is_error:
            raise KickAPIError(response.status_code, response.text)

    async def _token_request(self, form: dict[str, str], now: datetime) -> OAuthToken:
        response = await self._http.post(
            f"{AUTH_BASE_URL}/oauth/token",
            data={**form, "client_id": self._client_id, "client_secret": self._client_secret},
        )
        if response.status_code in {400, 401}:
            raise KickAuthError(f"token request rejected: {response.text}")
        if response.is_error:
            raise KickAPIError(response.status_code, response.text)
        payload = response.json()
        return OAuthToken(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token") or None,
            expires_at=now + timedelta(seconds=int(payload["expires_in"])),
            scope=payload.get("scope", ""),
        )


def utc_now() -> datetime:
    """Return the current time in UTC. Injected so tests control the clock."""
    return datetime.now(UTC)
