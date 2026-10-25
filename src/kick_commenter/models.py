"""Shared data contracts passed between modules.

Every module accepts and returns these models, so any algorithm can be
replaced as long as it keeps these shapes. Contract tests guard them.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    """Base for all shared models: immutable and strict about unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Sender(Contract):
    """A chat participant."""

    user_id: int
    username: str = Field(min_length=1)


class ChatMessage(Contract):
    """A single message sent in a channel's chat."""

    message_id: str = Field(min_length=1)
    channel_id: int
    sender: Sender
    text: str
    sent_at: datetime
    replies_to: str | None = None


class ChannelEventKind(StrEnum):
    """Channel events the bot may react to."""

    FOLLOW = "follow"
    SUBSCRIPTION = "subscription"
    GIFTED_SUBSCRIPTIONS = "gifted_subscriptions"
    RAID = "raid"
    KICKS_GIFTED = "kicks_gifted"
    STREAM_STARTED = "stream_started"
    STREAM_ENDED = "stream_ended"


class ChannelEvent(Contract):
    """Something that happened in a channel other than a chat message."""

    channel_id: int
    kind: ChannelEventKind
    occurred_at: datetime
    actor: Sender | None = None
