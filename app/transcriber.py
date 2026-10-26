"""Thin wrapper around faster-whisper.

The model is loaded once (via load_model) and reused for every transcription.
"""

import logging
import os
import threading
from dataclasses import dataclass
from typing import Optional

from faster_whisper import WhisperModel

from app.config import get_settings

logger = logging.getLogger(__name__)

_model: Optional[WhisperModel] = None
_model_lock = threading.Lock()


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str
    duration: float


def load_model() -> WhisperModel:
    """Load the Whisper model once and return the shared instance."""
    global _model
    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model

        settings = get_settings()
        os.makedirs(settings.model_cache_dir, exist_ok=True)
        logger.info(
            "Loading Whisper model size=%s device=%s compute_type=%s cache_dir=%s",
            settings.model_size,
            settings.device,
            settings.compute_type,
            settings.model_cache_dir,
        )
        _model = WhisperModel(
            settings.model_size,
            device=settings.device,
            compute_type=settings.compute_type,
            cpu_threads=settings.cpu_threads,
            download_root=settings.model_cache_dir,
        )
        logger.info("Whisper model loaded")
        return _model


def is_model_loaded() -> bool:
    """Return True once the model has been loaded."""
    return _model is not None


def transcribe_file(path: str) -> TranscriptionResult:
    """Transcribe the audio file at `path` and return text, language and duration."""
    model = load_model()
    segments, info = model.transcribe(path)
    text = " ".join(segment.text.strip() for segment in segments).strip()
    return TranscriptionResult(
        text=text,
        language=info.language,
        duration=float(info.duration),
    )