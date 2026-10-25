"""The interface every chat source implements."""

from collections.abc import AsyncIterator
from typing import Protocol

from kick_commenter.models import ChannelEvent, ChatMessage

ChatItem = ChatMessage | ChannelEvent


class ChatSource(Protocol):
    """Yields chat messages and channel events until the connection ends."""

    def stream(self) -> AsyncIterator[ChatItem]:
        """Connect and yield items as they arrive. Returns when the connection closes."""
        ...
