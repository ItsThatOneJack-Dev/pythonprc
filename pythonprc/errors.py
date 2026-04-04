from __future__ import annotations


# Map of API error codes to human-readable descriptions
ERLC_ERROR_DESCRIPTIONS: dict[int, str] = {
    0:    "Unknown error occurred.",
    1001: "Error communicating with Roblox / the in-game private server.",
    1002: "Internal system error.",
    2000: "No server-key provided.",
    2001: "Incorrectly formatted server-key.",
    2002: "Invalid or expired server-key.",
    2003: "Invalid global API key.",
    2004: "Server-key is banned from accessing the API.",
    3001: "No valid command provided in request body.",
    3002: "Server is currently offline (no players).",
    4001: "You are being rate limited.",
    4002: "Command is restricted.",
    4003: "Message is prohibited.",
    9998: "Resource is restricted.",
    9999: "In-game module is out of date — kick all players and try again.",
}


class ERLCError(Exception):
    """Base exception for all ERLC API errors."""

    def __init__(self, message: str, *, code: int | None = None, http_status: int | None = None):
        self.code = code
        self.http_status = http_status
        description = ERLC_ERROR_DESCRIPTIONS.get(code or -1, "")
        full = f"{message} (code={code}, http={http_status})" if code else message
        if description:
            full = f"{full} — {description}"
        super().__init__(full)


class AuthenticationError(ERLCError):
    """Raised when authentication fails (HTTP 403, error codes 2000–2004)."""


class InvalidServerKeyError(AuthenticationError):
    """Raised specifically for invalid/expired server keys (codes 2001, 2002)."""


class RateLimitError(ERLCError):
    """Raised on HTTP 429. Carries retry_after in seconds."""

    def __init__(self, message: str, retry_after: float, bucket: str | None = None):
        self.retry_after = retry_after
        self.bucket = bucket
        super().__init__(message, code=4001, http_status=429)


class ServerOfflineError(ERLCError):
    """Raised when the target private server has no players (HTTP 422, code 3002)."""


class CommandRestrictedError(ERLCError):
    """Raised when a command is restricted (code 4002)."""


class OutdatedModuleError(ERLCError):
    """Raised when the in-game module is out of date (code 9999)."""