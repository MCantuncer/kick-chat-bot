from collections.abc import Callable

import pytest

from kick_commenter.registry import Registry


def test_register_adds_component_when_name_is_new() -> None:
    registry: Registry[int] = Registry("scorer")

    registry.register("length")(3)

    assert registry.get("length") == 3
    assert registry.names() == ["length"]
    assert list(registry) == [3]
    assert len(registry) == 1


def test_register_rejects_component_when_name_is_taken() -> None:
    registry: Registry[int] = Registry("scorer")
    registry.register("length")(3)

    with pytest.raises(ValueError, match="already registered"):
        registry.register("length")(4)


def test_get_raises_when_name_is_unknown() -> None:
    registry: Registry[int] = Registry("filter")

    with pytest.raises(KeyError, match="unknown filter 'links'"):
        registry.get("links")


def test_register_returns_component_so_it_works_as_decorator() -> None:
    registry: Registry[Callable[[], str]] = Registry("source")

    @registry.register("templates")
    def templates() -> str:
        return "ok"

    assert templates() == "ok"
    assert registry.get("templates") is templates
