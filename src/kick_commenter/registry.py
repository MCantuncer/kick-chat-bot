"""A small plugin registry so new components plug in without editing shared lists."""

from collections.abc import Callable, Iterator


class Registry[T]:
    """Holds named components of one kind, such as scorers or filters."""

    def __init__(self, kind: str) -> None:
        """Create an empty registry for components of the given ``kind``."""
        self._kind = kind
        self._items: dict[str, T] = {}

    def register(self, name: str) -> Callable[[T], T]:
        """Return a decorator that adds a component under ``name``."""

        def decorator(item: T) -> T:
            if name in self._items:
                msg = f"{self._kind} {name!r} is already registered"
                raise ValueError(msg)
            self._items[name] = item
            return item

        return decorator

    def get(self, name: str) -> T:
        """Return the component registered under ``name``."""
        try:
            return self._items[name]
        except KeyError:
            msg = f"unknown {self._kind} {name!r}"
            raise KeyError(msg) from None

    def names(self) -> list[str]:
        """Return all registered names in registration order."""
        return list(self._items)

    def __iter__(self) -> Iterator[T]:
        """Iterate over registered components in registration order."""
        return iter(self._items.values())

    def __len__(self) -> int:
        """Return how many components are registered."""
        return len(self._items)
