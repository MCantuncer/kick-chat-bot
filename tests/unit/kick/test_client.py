import httpx
import pytest
import respx

from kick_commenter.kick.client import KickApi
from kick_commenter.kick.errors import KickAPIError, KickAuthError, KickRateLimitedError

API = "https://api.kick.com/public/v1"


class RecordingTokens:
    def __init__(self) -> None:
        self.forced = 0

    async def access_token(self, *, force_refresh: bool = False) -> str:
        if force_refresh:
            self.forced += 1
        return f"token-{self.forced}"


@pytest.fixture
def tokens() -> RecordingTokens:
    return RecordingTokens()


@pytest.fixture
def api(http: httpx.AsyncClient, tokens: RecordingTokens) -> KickApi:
    return KickApi(http, tokens)


@respx.mock
async def test_current_user_reads_first_user(api: KickApi) -> None:
    route = respx.get(f"{API}/users").mock(
        return_value=httpx.Response(200, json={"data": [{"user_id": 7, "name": "golfwangtr"}]})
    )

    user = await api.current_user()

    assert (user.user_id, user.name) == (7, "golfwangtr")
    assert route.calls.last.request.headers["Authorization"] == "Bearer token-0"


@respx.mock
async def test_channels_by_slug_sends_each_slug_and_reads_live_state(api: KickApi) -> None:
    route = respx.get(f"{API}/channels").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"broadcaster_user_id": 1, "slug": "a", "stream": {"is_live": True}},
                    {"broadcaster_user_id": 2, "slug": "b", "stream": None},
                ]
            },
        )
    )

    channels = await api.channels_by_slug(["a", "b"])

    assert route.calls.last.request.url.params.get_list("slug") == ["a", "b"]
    assert [(c.slug, c.is_live) for c in channels] == [("a", True), ("b", False)]


@respx.mock
async def test_request_retries_once_with_refreshed_token_after_401(
    api: KickApi, tokens: RecordingTokens
) -> None:
    respx.get(f"{API}/users").mock(
        side_effect=[
            httpx.Response(401),
            httpx.Response(200, json={"data": [{"user_id": 1, "name": "x"}]}),
        ]
    )

    await api.current_user()

    assert tokens.forced == 1


@respx.mock
async def test_request_raises_auth_error_when_401_persists(api: KickApi) -> None:
    respx.get(f"{API}/users").mock(return_value=httpx.Response(401))

    with pytest.raises(KickAuthError):
        await api.current_user()


@pytest.mark.parametrize(("header", "expected"), [("12", 12.0), ("soon", None), (None, None)])
@respx.mock
async def test_request_raises_rate_limited_with_retry_after(
    api: KickApi, header: str | None, expected: float | None
) -> None:
    headers = {"Retry-After": header} if header is not None else {}
    respx.get(f"{API}/users").mock(return_value=httpx.Response(429, headers=headers))

    with pytest.raises(KickRateLimitedError) as error:
        await api.current_user()

    assert error.value.retry_after == expected


@respx.mock
async def test_request_raises_api_error_on_other_failures(api: KickApi) -> None:
    respx.get(f"{API}/users").mock(return_value=httpx.Response(500, text="boom"))

    with pytest.raises(KickAPIError, match="500"):
        await api.current_user()
