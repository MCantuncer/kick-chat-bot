"""Where bot tokens are kept: the operating system keychain, never a plain file."""

from typing import Protocol

import keyring

from kick_commenter.kick.oauth import OAuthToken

KEYRING_SERVICE = "kick-commenter"


class TokenStore(Protocol):
    """Saves and loads tokens by key."""

    def load(self, key: str) -> OAuthToken | None:
        """Return the stored token, or ``None`` when there is none."""
        ...

    def save(self, key: str, token: OAuthToken) -> None:
        """Store or replace the token."""
        ...

    def delete(self, key: str) -> None:
        """Remove the token if present."""
        ...


class KeyringTokenStore:
    """Token store backed by the OS keychain through ``keyring``."""

    def load(self, key: str) -> OAuthToken | None:
        """Return the stored token, or ``None`` when there is none."""
        raw = keyring.get_password(KEYRING_SERVICE, key)
        return OAuthToken.model_validate_json(raw) if raw else None

    def save(self, key: str, token: OAuthToken) -> None:
        """Store or replace the token."""
        keyring.set_password(KEYRING_SERVICE, key, token.model_dump_json())

    def delete(self, key: str) -> None:
        """Remove the token if present."""
        if keyring.get_password(KEYRING_SERVICE, key) is not None:
            keyring.delete_password(KEYRING_SERVICE, key)


class MemoryTokenStore:
    """In-memory token store for tests."""

    def __init__(self) -> None:
        """Start empty."""
        self._tokens: dict[str, OAuthToken] = {}

    def load(self, key: str) -> OAuthToken | None:
        """Return the stored token, or ``None`` when there is none."""
        return self._tokens.get(key)

    def save(self, key: str, token: OAuthToken) -> None:
        """Store or replace the token."""
        self._tokens[key] = token

    def delete(self, key: str) -> None:
        """Remove the token if present."""
        self._tokens.pop(key, None)
