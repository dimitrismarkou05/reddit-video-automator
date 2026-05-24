"""Local TTS model API routes."""

import threading
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from core.database import get_db
from services.tts_service import TTSService
from services.notification_service import NotificationService
from tts_local.schemas import TtsStatusResponse
from tts_local.sse import reset_install_state

router = APIRouter()

_install_lock = threading.Lock()
_install_running = False


@router.get("/status", response_model=TtsStatusResponse)
def get_tts_status(db: Session = Depends(get_db)):
    service = TTSService(db)
    return service.get_status()


@router.get("/voices")
def list_voices(db: Session = Depends(get_db)):
    service = TTSService(db)
    return service.list_voices()


@router.post("/install")
def install_tts(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    global _install_running

    service = TTSService(db)
    status = service.get_status()
    if status["installed"]:
        return {
            "success": True,
            "message": "TTS model already installed.",
            "status": status,
        }

    with _install_lock:
        if _install_running:
            return {
                "success": False,
                "message": "Installation already in progress.",
            }
        _install_running = True

    reset_install_state()
    background_tasks.add_task(_run_install_sync)

    return {
        "success": True,
        "message": "Installation started.",
    }


@router.post("/retry")
def retry_install(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    global _install_running

    with _install_lock:
        if _install_running:
            return {
                "success": False,
                "message": "Installation already in progress.",
            }
        _install_running = True

    reset_install_state()
    background_tasks.add_task(_run_install_sync)

    return {"success": True, "message": "Retrying installation..."}


def _run_install_sync():
    global _install_running
    from core.database import SessionLocal

    db = SessionLocal()
    try:
        service = TTSService(db)
        notif_service = NotificationService(db)
        result = service.install_sync()

        if result.get("success"):
            notif_service.create(
                notif_type="tts",
                level="success",
                message="TTS model installed successfully",
                details={"model_name": result.get("model_name")},
            )
        else:
            error = result.get("error", "Unknown error")
            notif_service.create(
                notif_type="tts",
                level="error",
                message=f"TTS installation failed: {error}",
                details={"error": error},
            )
    except Exception as exc:
        try:
            notif_service = NotificationService(db)
            notif_service.create(
                notif_type="tts",
                level="error",
                message=f"TTS installation crashed: {str(exc)}",
                details={"error": str(exc)},
            )
        except Exception:
            pass
    finally:
        db.close()
        with _install_lock:
            _install_running = False


@router.post("/cancel")
def cancel_installation(db: Session = Depends(get_db)):
    service = TTSService(db)
    notif_service = NotificationService(db)

    service.cancel_install()

    notif_service.create(
        notif_type="tts",
        level="warning",
        message="TTS installation cancelled by user",
    )

    return {"success": True, "message": "Installation cancelled"}
