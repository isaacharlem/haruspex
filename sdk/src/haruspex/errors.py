"""SDK exceptions. These never propagate into the user's training loop; the
background worker catches them, logs, and retries or buffers."""


class HaruspexError(Exception):
    """Base class for SDK errors."""


class HaruspexAPIError(HaruspexError):
    """Non-2xx response from the Haruspex API."""

    def __init__(self, status_code: int, code: str, message: str, request_id: str | None = None):
        super().__init__(f"[{status_code}] {code}: {message}")
        self.status_code = status_code
        self.code = code
        self.message = message
        self.request_id = request_id

    @property
    def retryable(self) -> bool:
        return self.status_code == 429 or self.status_code >= 500


class HaruspexConnectionError(HaruspexError):
    """The API was unreachable (always retryable)."""
