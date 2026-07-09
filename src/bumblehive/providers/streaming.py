import logging
import os


logger = logging.getLogger(__name__)

STREAM_IDLE_TIMEOUT_ENV = "BUMBLEHIVE_STREAM_IDLE_TIMEOUT_S"
DEFAULT_STREAM_IDLE_TIMEOUT_S = 90.0
MAX_STREAM_IDLE_TIMEOUT_S = 3600.0


def resolve_stream_idle_timeout_s(
    *,
    env_value: str | None = None,
    default: float = DEFAULT_STREAM_IDLE_TIMEOUT_S,
    maximum: float = MAX_STREAM_IDLE_TIMEOUT_S,
) -> float:
    """Return a bounded streaming idle timeout in seconds."""
    raw = os.environ.get(STREAM_IDLE_TIMEOUT_ENV) if env_value is None else env_value
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Ignoring invalid %s=%r; using %s",
            STREAM_IDLE_TIMEOUT_ENV,
            raw,
            default,
        )
        return default
    if value <= 0:
        logger.warning(
            "Ignoring non-positive %s=%r; using %s",
            STREAM_IDLE_TIMEOUT_ENV,
            raw,
            default,
        )
        return default
    if value > maximum:
        logger.warning(
            "Clamping %s=%r to %s",
            STREAM_IDLE_TIMEOUT_ENV,
            raw,
            maximum,
        )
        return maximum
    return value
