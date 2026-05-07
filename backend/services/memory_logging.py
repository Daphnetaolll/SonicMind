from __future__ import annotations

import logging
import os
import resource
from typing import Any


LOGGER = logging.getLogger("sonicmind.memory")
LOGGER.setLevel(logging.INFO)
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(_handler)
LOGGER.propagate = False


def _memory_logs_enabled() -> bool:
    # Keep production memory logs configurable without involving any secret values.
    return os.getenv("SONICMIND_MEMORY_LOGS", "true").strip().lower() not in {"0", "false", "no"}


def rss_mb() -> float:
    """Return current process RSS in megabytes using psutil when available."""
    try:
        import psutil

        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except Exception:
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if os.uname().sysname == "Darwin":
            return usage / (1024 * 1024)
        return usage / 1024


def log_memory(stage: str, **fields: Any) -> None:
    # Log only diagnostic labels and numeric/string context that cannot contain credentials.
    if not _memory_logs_enabled():
        return

    safe_fields = " ".join(
        f"{key}={value}"
        for key, value in fields.items()
        if isinstance(value, (int, float, bool, str)) and key.lower() not in {"token", "api_key", "password", "secret"}
    )
    suffix = f" {safe_fields}" if safe_fields else ""
    LOGGER.info("[MEMORY] stage=%s rss_mb=%.1f%s", stage, rss_mb(), suffix)
