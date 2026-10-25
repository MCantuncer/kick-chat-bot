from collections.abc import AsyncIterator

import httpx
import pytest

from kick_commenter.kick.oauth import OAuthClient


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def oauth(http: httpx.AsyncClient) -> OAuthClient:
    return OAuthClient(http, "client-id", "client-secret", "http://localhost:8765/callback")
