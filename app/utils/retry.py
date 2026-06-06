import functools

import anthropic
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

# LegiScan permanent errors — no point retrying these
_LEGISCAN_PERMANENT = (
    "Unknown bill id",
    "Invalid bill id",
    "Unknown state",
    "API key has exceeded",  # monthly quota exhausted — stop immediately
)

# Anthropic errors that will never succeed on retry
_ANTHROPIC_PERMANENT = (
    anthropic.NotFoundError,
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
)


def _is_retryable(exc: BaseException) -> bool:
    """Return False for permanent API errors that should not be retried."""
    if isinstance(exc, _ANTHROPIC_PERMANENT):
        return False
    msg = str(exc)
    return not any(p in msg for p in _LEGISCAN_PERMANENT)


def retry_with_backoff(max_attempts: int = 3, base_delay: float = 1.0):
    """Decorator: retry with exponential backoff. Use on all external API calls."""
    def decorator(func):
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=base_delay, min=base_delay, max=30),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        )
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    return decorator
