"""Asks kick.com which public chat stream app to connect to.

Kick rotates the stream's app key from time to time. The website asks for the
current one before it connects, and so do we. A known key is the fallback.
"""

import logging

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from kick_commenter.collector.lookup import BROWSER_HEADERS

logger = logging.getLogger(__name__)

REALTIME_URL = "https://web.kick.com/api/v1/realtime/channels/{channel_id}/chat/connection"
CONNECTION_REQUEST = {
    "client": {"id": "kick-commenter", "type": "web"},
    "capabilities": {"accepted_providers": [{"provider": "pusher"}]},
}


class PusherApp(BaseModel):
    """Which stream app to connect to."""

    model_config = ConfigDict(frozen=True)

    app_key: str
    cluster: str

    @property
    def url(self) -> str:
        """The websocket address for this app."""
        return (
            f"wss://ws-{self.cluster}.pusher.com/app/{self.app_key}"
            "?protocol=7&client=js&version=8.4.0&flash=false"
        )


FALLBACK_APP = PusherApp(app_key="34bf7a0ff419a2a775b9", cluster="us2")


class _Credentials(BaseModel):
    app_key: str = ""
    cluster: str = ""


class _Connection(BaseModel):
    provider: str
    credentials: _Credentials = _Credentials()


class _Data(BaseModel):
    connections: list[_Connection] = []


class _Response(BaseModel):
    data: _Data


class RealtimeConfig:
    """Finds the stream app for a channel, falling back to a known one."""

    def __init__(self, http: httpx.AsyncClient, fallback: PusherApp = FALLBACK_APP) -> None:
        """Ask kick.com through ``http``; use ``fallback`` when that fails."""
        self._http = http
        self._fallback = fallback

    async def pusher_app(self, channel_id: int) -> PusherApp:
        """Return the stream app to use for ``channel_id``. Never raises."""
        try:
            response = await self._http.post(
                REALTIME_URL.format(channel_id=channel_id),
                json=CONNECTION_REQUEST,
                headers={**BROWSER_HEADERS, "Origin": "https://kick.com"},
            )
            response.raise_for_status()
            connections = _Response.model_validate_json(response.content).data.connections
        except (httpx.HTTPError, ValidationError) as error:
            logger.warning("could not ask kick.com for the chat stream app (%s)", error)
            return self._fallback
        for connection in connections:
            credentials = connection.credentials
            if connection.provider == "pusher" and credentials.app_key and credentials.cluster:
                return PusherApp(app_key=credentials.app_key, cluster=credentials.cluster)
        logger.warning("kick.com offered no public chat stream app; using the known one")
        return self._fallback
