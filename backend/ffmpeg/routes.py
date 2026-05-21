"""FFmpeg feature API routes."""

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from core.database import get_db
from services.ffmpeg_service import FfmpegService
from services.notification_service import NotificationService
from ffmpeg.schemas import (
    FfmpegStatusResponse,
    SetPathRequest,
    CheckPathResponse,
    InstallRequest,
)
from ffmpeg.sse import reset_install_state

router = APIRouter()


@router.get("/status", response_model=FfmpegStatusResponse)
def get_ffmpeg_status(db: Session = Depends(get_db)):
    """Check FFmpeg installation status."""
    service = FfmpegService(db)
    return service.get_status()


@router.post("/install")
def install_ffmpeg(
    background_tasks: BackgroundTasks,
    request: InstallRequest = None,
    db: Session = Depends(get_db),
):
    """Start FFmpeg installation. Returns immediately; progress streams via SSE."""
    service = FfmpegService(db)

    # Check if already installed
    status = service.get_status()
    if status["can_generate_videos"] and not (request and request.force):
        return {
            "success": True,
            "message": "FFmpeg is already installed.",
            "status": status,
        }

    reset_install_state()
    notif_service = NotificationService(db)
    background_tasks.add_task(_run_install_sync, service, notif_service)

    return {
        "success": True,
        "message": "Installation started. Connect to /sse/ffmpeg/install-progress for updates.",
    }


@router.post("/retry")
def retry_install(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Retry FFmpeg installation."""
    service = FfmpegService(db)
    notif_service = NotificationService(db)
    reset_install_state()
    background_tasks.add_task(_run_install_sync, service, notif_service)

    return {"success": True, "message": "Retrying installation..."}


def _run_install_sync(service: FfmpegService, notif_service: NotificationService):
    """Synchronous wrapper for the async install method, suitable for BackgroundTasks."""
    import asyncio
    try:
        result = asyncio.run(service.install())
        if result.get("success"):
            notif_service.create(
                notif_type="ffmpeg",
                level="success",
                message="FFmpeg installed successfully",
                details={"ffmpeg_path": result.get("ffmpeg_path")},
            )
        else:
            error = result.get("error", "Unknown error")
            notif_service.create(
                notif_type="ffmpeg",
                level="error",
                message=f"FFmpeg installation failed: {error}",
                details={"error": error},
            )
    except Exception as exc:
        notif_service.create(
            notif_type="ffmpeg",
            level="error",
            message=f"FFmpeg installation crashed: {str(exc)}",
            details={"error": str(exc)},
        )


@router.post("/set-path", response_model=CheckPathResponse)
def set_ffmpeg_path(request: SetPathRequest, db: Session = Depends(get_db)):
    """Manually set custom FFmpeg/FFprobe paths."""
    service = FfmpegService(db)
    notif_service = NotificationService(db)

    result = service.set_custom_paths(request.ffmpeg_path, request.ffprobe_path)

    if result["valid"]:
        notif_service.create(
            notif_type="ffmpeg",
            level="success",
            message="FFmpeg path set successfully",
            details={
                "ffmpeg_path": request.ffmpeg_path,
                "ffprobe_path": request.ffprobe_path,
            },
        )
        return CheckPathResponse(
            valid=True,
            ffmpeg_version=result.get("ffmpeg_version"),
            ffprobe_version=result.get("ffprobe_version"),
        )
    else:
        notif_service.create(
            notif_type="ffmpeg",
            level="warning",
            message=f"Invalid FFmpeg path: {result.get('error')}",
        )
        return CheckPathResponse(valid=False, error=result.get("error"))


@router.get("/check-path", response_model=CheckPathResponse)
def check_ffmpeg_path(path: str, db: Session = Depends(get_db)):
    """Validate a custom binary path."""
    service = FfmpegService(db)
    result = service.check_path(path)
    return CheckPathResponse(
        valid=result["valid"],
        ffmpeg_version=result.get("ffmpeg_version"),
        ffprobe_version=result.get("ffprobe_version"),
        error=result.get("error"),
    )


@router.delete("/reset")
def reset_ffmpeg_paths(db: Session = Depends(get_db)):
    """Reset to auto-detected paths."""
    service = FfmpegService(db)
    notif_service = NotificationService(db)

    status = service.reset_paths()

    notif_service.create(
        notif_type="ffmpeg",
        level="info",
        message="FFmpeg paths reset to auto-detected defaults",
    )

    return status


@router.post("/cancel")
def cancel_installation(db: Session = Depends(get_db)):
    """Cancel an in-progress installation."""
    service = FfmpegService(db)
    notif_service = NotificationService(db)

    service.cancel_install()

    notif_service.create(
        notif_type="ffmpeg",
        level="warning",
        message="FFmpeg installation cancelled by user",
    )

    return {"success": True, "message": "Installation cancelled"}