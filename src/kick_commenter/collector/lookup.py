"""Finds the chatroom id the public chat stream needs for a channel name."""

import json
from pathlib import Path

import httpx
from pydantic import BaseModel, TypeAdapter

CHANNEL_PAGE_URL = "https://kick.com/api/v2/channels/{slug}"
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
HTTP_NOT_FOUND = 404


class ChannelIds(BaseModel):
    """The ids the stream needs for one channel."""

    slug: str
    channel_id: int
    chatroom_id: int


class ChannelLookupError(Exception):
    """The channel could not be resolved."""


_CACHE = TypeAdapter(dict[str, ChannelIds])


class ChannelLookup:
    """Resolves channel names to stream ids, caching results on disk."""

    def __init__(self, http: httpx.AsyncClient, cache_file: Path) -> None:
        """Use ``http`` for lookups and keep results in ``cache_file``."""
        self._http = http
        self._cache_file = cache_file

    async def resolve(self, slug: str) -> ChannelIds:
        """Return the ids for ``slug``, from cache when known."""
        key = slug.lower().lstrip("@")
        cache = self._load()
        if key in cache:
            return cache[key]
        ids = await self._fetch(key)
        self.remember(ids)
        return ids

    def remember(self, ids: ChannelIds) -> None:
        """Save ids to the cache, for example when the user passes them by hand."""
        cache = self._load()
        cache[ids.slug] = ids
        self._cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._cache_file.write_text(
            json.dumps(_CACHE.dump_python(cache, mode="json"), indent=2), encoding="utf-8"
        )

    async def _fetch(self, slug: str) -> ChannelIds:
        try:
            response = await self._http.get(
                CHANNEL_PAGE_URL.format(slug=slug), headers=BROWSER_HEADERS
            )
        except httpx.HTTPError as error:
            msg = f"could not reach kick.com: {error}"
            raise ChannelLookupError(msg) from error
        if response.status_code == HTTP_NOT_FOUND:
            msg = f"no channel named {slug!r}"
            raise ChannelLookupError(msg)
        if response.is_error:
            msg = (
                f"kick.com refused the lookup ({response.status_code}). "
                "Pass --chatroom-id and --channel-id to skip it."
            )
            raise ChannelLookupError(msg)
        payload = response.json()
        chatroom = payload.get("chatroom") or {}
        if not chatroom.get("id"):
            msg = f"channel {slug!r} has no chatroom"
            raise ChannelLookupError(msg)
        return ChannelIds(slug=slug, channel_id=int(payload["id"]), chatroom_id=int(chatroom["id"]))

    def _load(self) -> dict[str, ChannelIds]:
        return read_cache(self._cache_file)


def read_cache(cache_file: Path) -> dict[str, ChannelIds]:
    """Return the channels resolved so far, by name."""
    if not cache_file.exists():
        return {}
    return _CACHE.validate_json(cache_file.read_bytes())
