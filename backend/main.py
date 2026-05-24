from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.database import init_db
from api_router import api_router
from notifications.sse import signal_shutdown
from video.engine.job_manager import job_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    try:
        from video.engine.subtitles import _load_whisper_model
        _load_whisper_model("base")
    except Exception:
        pass

    try:
        from services.tts_service import TTSService
        from core.database import SessionLocal
        db = SessionLocal()
        try:
            tts_service = TTSService(db)
            tts_service.preload_default()
        finally:
            db.close()
    except Exception:
        pass

    yield

    signal_shutdown()

    paused_ids = job_manager.shutdown_all()

    try:
        from core.database import SessionLocal
        from video.models import GeneratedVideo, VideoStatus
        db = SessionLocal()
        try:
            for vid_id in paused_ids:
                video = db.query(GeneratedVideo).filter(
                    GeneratedVideo.id == vid_id
                ).first()
                if video and video.status not in (
                    VideoStatus.DONE.value,
                    VideoStatus.FAILED.value,
                    VideoStatus.CANCELLED.value,
                ):
                    video.status = VideoStatus.PAUSED.value
                    video.is_paused = True
            db.commit()
        finally:
            db.close()
    except Exception:
        pass


app = FastAPI(
    title="Reddit Video Automator API",
    description="Orchestration layer for Reddit story -> YouTube video pipeline",
    version="0.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "app://rva"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def root():
    return {
        "message": "Reddit Video Automator API",
        "version": "0.4.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health():
    return {"status": "ok", "sse": True}