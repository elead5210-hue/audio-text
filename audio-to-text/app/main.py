"""FastAPI application exposing GET /health and POST /transcribe."""

import logging
import os
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse

from app.config import get_settings
from app.transcriber import is_model_loaded, load_model, transcribe_file

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024
INDEX_HTML_PATH = Path(__file__).resolve().parent / "static" / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the Whisper model once at startup."""
    os.makedirs(settings.temp_dir, exist_ok=True)
    logger.info("Starting up: loading model")
    await run_in_threadpool(load_model)
    logger.info("Startup complete")
    yield
    logger.info("Shutting down")


app = FastAPI(title="audio-to-text", lifespan=lifespan)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    """Serve the single-page client from the same origin as the API."""
    if not INDEX_HTML_PATH.is_file():
        raise HTTPException(status_code=404, detail="Client page not found.")
    return FileResponse(INDEX_HTML_PATH, media_type="text/html")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "model_loaded": is_model_loaded()}


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)) -> JSONResponse:
    started = time.monotonic()
    filename = file.filename or ""
    logger.info("Transcribe request received: filename=%r content_type=%r", filename, file.content_type)

    extension = os.path.splitext(filename)[1].lower()
    if extension not in settings.allowed_extensions:
        allowed = ", ".join(sorted(settings.allowed_extensions))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '{extension}'. Allowed: {allowed}.",
        )

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in settings.allowed_content_types:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported content type '{content_type}'.",
        )

    tmp_path = None
    try:
        os.makedirs(settings.temp_dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(suffix=extension, dir=settings.temp_dir)
        total = 0
        with os.fdopen(fd, "wb") as tmp:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    limit_mb = settings.max_upload_bytes // (1024 * 1024)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum size is {limit_mb} MB.",
                    )
                tmp.write(chunk)

        if total == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        try:
            result = await run_in_threadpool(transcribe_file, tmp_path)
        except Exception:
            logger.exception("Transcription failed for %r", filename)
            raise HTTPException(
                status_code=422,
                detail="Could not transcribe the uploaded audio. The file may be corrupt or not valid audio.",
            )

        elapsed = time.monotonic() - started
        logger.info(
            "Transcribe done: filename=%r bytes=%d audio_duration=%.1fs processing=%.1fs language=%s",
            filename,
            total,
            result.duration,
            elapsed,
            result.language,
        )
        return JSONResponse(
            {
                "text": result.text,
                "language": result.language,
                "duration": result.duration,
            }
        )
    except HTTPException as exc:
        logger.warning("Transcribe rejected: status=%d detail=%s", exc.status_code, exc.detail)
        raise
    except Exception:
        logger.exception("Unexpected error handling %r", filename)
        raise HTTPException(status_code=500, detail="Internal server error.")
    finally:
        await file.close()
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                logger.warning("Failed to remove temp file %s", tmp_path)