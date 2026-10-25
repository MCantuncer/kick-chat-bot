"""Errors raised when talking to Kick."""


class KickError(Exception):
    """Base class for all Kick API errors."""


class KickAuthError(KickError):
    """The token is missing, expired beyond refresh, or was rejected."""


class KickRateLimitedError(KickError):
    """Kick answered 429. ``retry_after`` is in seconds when Kick sent it."""

    def __init__(self, retry_after: float | None) -> None:
        """Store how long Kick asked us to wait."""
        super().__init__(f"rate limited by Kick (retry after {retry_after}s)")
        self.retry_after = retry_after


class KickAPIError(KickError):
    """Any other unsuccessful response from Kick."""

    def __init__(self, status_code: int, body: str) -> None:
        """Store the status code and the response body."""
        super().__init__(f"Kick API error {status_code}: {body}")
        self.status_code = status_code
        self.body = body
