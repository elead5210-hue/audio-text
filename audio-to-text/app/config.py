"""Runtime configuration read from environment variables.

All values have safe defaults. The listen port defaults to 8000 and is read from
LISTEN_PORT only; PORT, APP_PORT, SERVER_PORT, HTTP_PORT and WEB_PORT are never read.
"""

import os
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from typing import FrozenSet


def _get_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _get_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        return default
    return value if value >= minimum else default


def _get_set(name: str, default: FrozenSet[str]) -> FrozenSet[str]:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    items = frozenset(item.strip().lower() for item in raw.split(",") if item.strip())
    return items if items else default


DEFAULT_ALLOWED_EXTENSIONS: FrozenSet[str] = frozenset({".ogg"})
DEFAULT_ALLOWED_CONTENT_TYPES: FrozenSet[str] = frozenset(
    {
        "audio/ogg",
        "application/ogg",
        "audio/x-ogg",
        "audio/opus",
        "video/ogg",
    }
)


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    model_size: str
    device: str
    compute_type: str
    cpu_threads: int
    model_cache_dir: str
    temp_dir: str
    max_upload_bytes: int
    allowed_extensions: FrozenSet[str]
    allowed_content_types: FrozenSet[str]
    log_level: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    base_tmp = tempfile.gettempdir()
    max_upload_mb = _get_int("MAX_UPLOAD_MB", 25)

    return Settings(
        host=_get_str("LISTEN_HOST", "0.0.0.0"),
        port=_get_int("LISTEN_PORT", 8000),
        model_size=_get_str("WHISPER_MODEL_SIZE", "base"),
        device=_get_str("WHISPER_DEVICE", "cpu"),
        compute_type=_get_str("WHISPER_COMPUTE_TYPE", "int8"),
        cpu_threads=_get_int("WHISPER_CPU_THREADS", 1),
        model_cache_dir=_get_str(
            "WHISPER_MODEL_CACHE_DIR", os.path.join(base_tmp, "whisper-models")
        ),
        temp_dir=_get_str("UPLOAD_TEMP_DIR", os.path.join(base_tmp, "uploads")),
        max_upload_bytes=max_upload_mb * 1024 * 1024,
        allowed_extensions=_get_set("ALLOWED_EXTENSIONS", DEFAULT_ALLOWED_EXTENSIONS),
        allowed_content_types=_get_set(
            "ALLOWED_CONTENT_TYPES", DEFAULT_ALLOWED_CONTENT_TYPES
        ),
        log_level=_get_str("LOG_LEVEL", "INFO").upper(),
    )