from collections.abc import Iterator

import keyring
import pytest
from keyring.backend import KeyringBackend

from kick_commenter.kick.token_store import KeyringTokenStore, MemoryTokenStore, TokenStore

from .factories import make_token


class InMemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self) -> None:
        super().__init__()  # type: ignore[no-untyped-call]
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        del self.values[(service, username)]


@pytest.fixture
def keyring_backend() -> Iterator[InMemoryKeyring]:
    previous = keyring.get_keyring()
    backend = InMemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture(params=["memory", "keyring"])
def store(
    request: pytest.FixtureRequest,
    keyring_backend: InMemoryKeyring,  # noqa: ARG001 - installs the fake keyring
) -> TokenStore:
    return MemoryTokenStore() if request.param == "memory" else KeyringTokenStore()


def test_store_round_trips_token(store: TokenStore) -> None:
    token = make_token()

    store.save("bot:1", token)

    assert store.load("bot:1") == token


def test_store_returns_none_and_deletes_quietly_when_missing(store: TokenStore) -> None:
    assert store.load("bot:404") is None
    store.delete("bot:404")


def test_store_delete_removes_token(store: TokenStore) -> None:
    store.save("bot:1", make_token())

    store.delete("bot:1")

    assert store.load("bot:1") is None


def test_keyring_store_uses_app_service_name(keyring_backend: InMemoryKeyring) -> None:
    KeyringTokenStore().save("bot:1", make_token())

    assert ("kick-commenter", "bot:1") in keyring_backend.values
