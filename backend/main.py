from contextlib import asynccontextmanager
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.database import init_db
from api_router import api_router
from notifications.sse import signal_shutdown
from video.engine.job_manager import job_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Startup helpers
# ---------------------------------------------------------------------------

def _seed_default_voice() -> None:
    """Ensure default_tts_voice setting exists in DB (fresh-install fix)."""
    try:
        from core.database import SessionLocal
        from core.settings_manager import SettingsManager
        from tts_local.mirrors import get_available_models

        db = SessionLocal()
        try:
            mgr = SettingsManager(db)
            current = mgr.get("default_tts_voice")
            models = get_available_models()
            valid_ids = {m["id"] for m in models}

            if not current or current not in valid_ids:
                default_id = models[0]["id"] if models else "en_ljspeech_tacotron2_ddc"
                mgr.set("default_tts_voice", default_id)
                db.commit()
                if not current:
                    logger.info(
                        f"[Lifespan] Seeded default_tts_voice = {default_id}"
                    )
                else:
                    logger.warning(
                        f"[Lifespan] default_tts_voice '{current}' is unknown; "
                        f"reset to {default_id}"
                    )
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"[Lifespan] Could not seed default voice: {exc}")


def _recover_orphan_active_videos() -> None:
    """Pause orphan active videos on cold start — no auto-resume after restart."""
    try:
        from core.database import SessionLocal
        from video.models import GeneratedVideo
        from video.engine.job_manager import ORPHAN_ACTIVE_STATUSES, persist_video_pause

        db = SessionLocal()
        try:
            orphans = (
                db.query(GeneratedVideo)
                .filter(GeneratedVideo.status.in_(ORPHAN_ACTIVE_STATUSES))
                .all()
            )
            paused_count = 0
            for video in orphans:
                if video.id in job_manager.active_jobs:
                    continue
                if persist_video_pause(video.id, reason="startup"):
                    paused_count += 1
            if paused_count:
                logger.info(
                    f"[Lifespan] Paused {paused_count} orphan active video(s) on startup"
                )
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"[Lifespan] Could not recover orphan active videos: {exc}")


async def _temp_sweeper_loop() -> None:
    """Periodically delete temp dirs for terminal/orphaned jobs."""
    SWEEP_INTERVAL = 3600  # 1 hour
    TTL_HOURS = 24

    while True:
        try:
            await asyncio.sleep(SWEEP_INTERVAL)
            await asyncio.to_thread(_sweep_temp_dirs, TTL_HOURS)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning(f"[TempSweeper] Error: {exc}")


def _sweep_temp_dirs(ttl_hours: int) -> None:
    from core.config import TEMP_DIR
    from core.database import SessionLocal
    from video.models import GeneratedVideo, VideoStatus

    TERMINAL = {
        VideoStatus.DONE.value,
        VideoStatus.FAILED.value,
        VideoStatus.CANCELLED.value,
    }
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=ttl_hours)
        removed = 0
        for d in Path(TEMP_DIR).iterdir():
            if not d.is_dir() or not d.name.startswith("video_"):
                continue
            try:
                vid_id = int(d.name.split("_")[1])
            except (IndexError, ValueError):
                continue
            # Check DB status.
            video = db.query(GeneratedVideo).filter(
                GeneratedVideo.id == vid_id
            ).first()
            should_delete = False
            if video and video.status in TERMINAL:
                should_delete = True
            elif video and video.status == VideoStatus.PAUSED.value:
                should_delete = False
            elif d.stat().st_mtime < cutoff.timestamp():
                should_delete = True
            if should_delete and vid_id not in job_manager.active_jobs:
                try:
                    import shutil
                    shutil.rmtree(str(d), ignore_errors=True)
                    removed += 1
                except Exception as exc:
                    logger.warning(f"[TempSweeper] Could not remove {d}: {exc}")
        if removed:
            logger.info(f"[TempSweeper] Removed {removed} stale temp dir(s)")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[Lifespan] Starting up…")
    from video.routes import set_app_event_loop
    set_app_event_loop(asyncio.get_running_loop())
    init_db()  # also runs _migrate_db()

    # Seed default voice so fresh installs never 404 on voice lookup.
    _seed_default_voice()

    # Inject locally installed FFmpeg into PATH before any jobs run.
    try:
        from ffmpeg import ensure_ffmpeg_in_path
        if ensure_ffmpeg_in_path():
            logger.info("[Lifespan] FFmpeg available on PATH")
        else:
            logger.warning(
                "[Lifespan] FFmpeg not on PATH — install via Settings before generating"
            )
    except Exception as exc:
        logger.warning(f"[Lifespan] FFmpeg PATH setup failed: {exc}")

    # Start the queue processor early (event loop is guaranteed here).
    job_manager._shutdown = False
    job_manager._ensure_queue_processor()
    logger.info("[Lifespan] Queue processor ensured")

    # Startup recovery: pause orphan active jobs (no auto-resume).
    _recover_orphan_active_videos()

    # Pre-load models in background tasks so the API is immediately responsive.
    async def _bg_preload_whisper():
        try:
            from video.engine.subtitles import _load_whisper_model
            from core.database import SessionLocal
            from core.settings_manager import SettingsManager
            db = SessionLocal()
            try:
                mgr = SettingsManager(db)
                size = mgr.get("whisper_model_size") or "base"
            finally:
                db.close()
            await asyncio.to_thread(_load_whisper_model, size)
            logger.info(f"[Lifespan] Whisper model ({size}) pre-loaded")
        except Exception as exc:
            logger.warning(f"[Lifespan] Whisper preload failed: {exc}")

    async def _bg_preload_tts():
        try:
            from tts_local.mirrors import get_default_model_name
            import video.engine.tts_registry as tts_registry
            model_name = get_default_model_name()
            await asyncio.to_thread(tts_registry.warmup, model_name)
            logger.info(f"[Lifespan] TTS warmup started for {model_name}")
        except Exception as exc:
            logger.warning(f"[Lifespan] TTS warmup failed: {exc}")

    # Fire and forget – don't block the startup.
    asyncio.create_task(_bg_preload_whisper(), name="preload_whisper")
    asyncio.create_task(_bg_preload_tts(), name="preload_tts")

    # Start temp sweeper.
    sweeper_task = asyncio.create_task(_temp_sweeper_loop(), name="temp_sweeper")

    logger.info("[Lifespan] Startup complete – API ready")

    yield

    # Shutdown.
    logger.info("[Lifespan] Shutting down…")
    signal_shutdown()
    sweeper_task.cancel()

    paused_ids = job_manager.shutdown_all()
    logger.info(f"[Lifespan] Paused {len(paused_ids)} active job(s)")

    try:
        from core.database import SessionLocal
        from video.models import GeneratedVideo, VideoStatus
        from video.engine.job_manager import persist_video_pause

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
                    persist_video_pause(vid_id, reason="shutdown")
        finally:
            db.close()
    except Exception as exc:
        logger.error(f"[Lifespan] Shutdown DB update error: {exc}")

    logger.info("[Lifespan] Shutdown complete")


app = FastAPI(
    title="Reddit Video Automator API",
    description="Orchestration layer for Reddit story → YouTube video pipeline",
    version="0.5.0",
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
        "version": "0.5.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "sse": True,
        "queue_size": len(job_manager._queue),
        "active_jobs": len(job_manager.active_jobs),
    }
