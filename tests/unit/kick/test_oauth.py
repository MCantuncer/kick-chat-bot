import base64
import hashlib
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx

from kick_commenter.kick.errors import KickAPIError, KickAuthError
from kick_commenter.kick.oauth import BOT_SCOPES, OAuthClient, PkcePair

from .factories import NOW, make_token, token_response

TOKEN_URL = "https://id.kick.com/oauth/token"


def test_pkce_challenge_is_s256_of_verifier() -> None:
    pkce = PkcePair.generate()

    digest = hashlib.sha256(pkce.verifier.encode()).digest()
    assert pkce.challenge == base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    assert PkcePair.generate().verifier != pkce.verifier


def test_authorize_url_carries_state_scopes_and_challenge(oauth: OAuthClient) -> None:
    pkce = PkcePair.generate()

    url = urlsplit(oauth.authorize_url("state-123", pkce, BOT_SCOPES))
    query = parse_qs(url.query)

    assert url.netloc == "id.kick.com"
    assert url.path == "/oauth/authorize"
    assert query["state"] == ["state-123"]
    assert query["code_challenge"] == [pkce.challenge]
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == ["http://localhost:8765/callback"]
    assert query["scope"] == ["user:read channel:read chat:write events:subscribe"]


@respx.mock
async def test_exchange_code_sends_verifier_and_returns_token(oauth: OAuthClient) -> None:
    route = respx.post(TOKEN_URL).mock(return_value=token_response())
    pkce = PkcePair.generate()

    token = await oauth.exchange_code("the-code", pkce, NOW)

    form = parse_qs(route.calls.last.request.content.decode())
    assert form["grant_type"] == ["authorization_code"]
    assert form["code"] == ["the-code"]
    assert form["code_verifier"] == [pkce.verifier]
    assert form["client_secret"] == ["client-secret"]
    assert token.access_token == "access-2"
    assert token.refresh_token == "refresh-2"
    assert token.expires_at == NOW + timedelta(seconds=3600)


@respx.mock
async def test_refresh_uses_refresh_grant(oauth: OAuthClient) -> None:
    route = respx.post(TOKEN_URL).mock(return_value=token_response())

    await oauth.refresh("refresh-1", NOW)

    form = parse_qs(route.calls.last.request.content.decode())
    assert form["grant_type"] == ["refresh_token"]
    assert form["refresh_token"] == ["refresh-1"]


@respx.mock
async def test_app_token_has_no_refresh_token(oauth: OAuthClient) -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "app", "expires_in": 60})
    )

    token = await oauth.app_token(NOW)

    assert token.access_token == "app"
    assert token.refresh_token is None


@respx.mock
async def test_token_request_raises_auth_error_when_rejected(oauth: OAuthClient) -> None:
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(400, json={"error": "Invalid request"}))

    with pytest.raises(KickAuthError):
        await oauth.refresh("bad", NOW)


@respx.mock
async def test_token_request_raises_api_error_on_server_error(oauth: OAuthClient) -> None:
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(503, text="down"))

    with pytest.raises(KickAPIError) as error:
        await oauth.app_token(NOW)

    assert error.value.status_code == 503


@respx.mock
async def test_revoke_sends_token_and_raises_on_failure(oauth: OAuthClient) -> None:
    route = respx.post("https://id.kick.com/oauth/revoke").mock(
        side_effect=[httpx.Response(200, text="OK"), httpx.Response(400)]
    )

    await oauth.revoke("tok")
    with pytest.raises(KickAPIError):
        await oauth.revoke("tok")

    assert route.calls[0].request.url.params["token"] == "tok"


def test_token_counts_as_expired_inside_safety_margin() -> None:
    assert not make_token(ttl=3600).is_expired(NOW)
    assert make_token(ttl=30).is_expired(NOW)
