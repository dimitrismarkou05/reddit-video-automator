from .detector import FfmpegDetector
from core.ffmpeg_settings import FFmpegSettings
from core.database import SessionLocal

def ensure_ffmpeg_in_path() -> bool:
    """
    Ensure FFmpeg/FFprobe binaries are in the environment PATH.
    Uses saved settings if available, otherwise auto-detects.
    Returns True if both binaries are usable.
    """
    # Try to get saved paths from DB first
    db = SessionLocal()
    try:
        settings = FFmpegSettings(db)
        ffmpeg_path = settings.get_ffmpeg_path()
        ffprobe_path = settings.get_ffprobe_path()
    except Exception:
        ffmpeg_path = ffprobe_path = None
    finally:
        db.close()

    # If not saved, auto-detect
    if not ffmpeg_path or not ffprobe_path:
        detector = FfmpegDetector()
        ffmpeg_path = detector.detect_ffmpeg()
        ffprobe_path = detector.detect_ffprobe(ffmpeg_path)

    if not ffmpeg_path or not ffprobe_path:
        return False

    # Reuse the existing injection method
    detector = FfmpegDetector()
    detector._inject_to_path(ffmpeg_path, ffprobe_path)
    return True