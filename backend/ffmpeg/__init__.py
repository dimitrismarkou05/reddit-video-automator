from .detector import FfmpegDetector
from core.ffmpeg_settings import FFmpegSettings
from core.database import SessionLocal


def ensure_ffmpeg_in_path() -> bool:
    """
    Ensure FFmpeg/FFprobe binaries are in the environment PATH.
    Uses FfmpegService resolution order: DB settings → app-local → auto-detect.
    Returns True if both binaries are usable and ffmpeg resolves on PATH.
    """
    db = SessionLocal()
    try:
        from services.ffmpeg_service import FfmpegService
        service = FfmpegService(db)
        status = service.get_status()
        return bool(
            status.get("can_generate_videos")
            and status.get("ffmpeg_in_path")
        )
    except Exception:
        return False
    finally:
        db.close()
