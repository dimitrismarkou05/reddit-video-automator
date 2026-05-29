"""Settings management routes."""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from settings.models import Setting
from settings.schemas import SettingsUpdate, SettingsResponse, SettingsBulkResponse
from core.settings_manager import SettingsManager
from core.ffmpeg_settings import FFmpegSettings

router = APIRouter()


@router.post("", response_model=SettingsResponse)
def set_setting(data: SettingsUpdate, db: Session = Depends(get_db)):
    mgr = SettingsManager(db)
    setting = mgr.set(data.key, data.value, encrypt_value=data.encrypt)
    return setting

@router.get("/batch/keys", response_model=Dict[str, Optional[str]])
def get_settings_batch(keys: str, db: Session = Depends(get_db)):
    """Get multiple settings at once. Pass keys as comma-separated query param."""
    mgr = SettingsManager(db)
    key_list = [k.strip() for k in keys.split(",") if k.strip()]
    result: Dict[str, Optional[str]] = {}
    for key in key_list:
        result[key] = mgr.get(key)
    return result


@router.get("/ffmpeg/video", response_model=Dict[str, Any])
def get_ffmpeg_video_settings(db: Session = Depends(get_db)):
    """Return all FFmpeg video generation settings in one call."""
    settings = FFmpegSettings(db)
    return settings.get_all_video_settings()


@router.post("/ffmpeg/video")
def set_ffmpeg_video_setting(data: SettingsUpdate, db: Session = Depends(get_db)):
    """Set a single FFmpeg video generation setting."""
    settings = FFmpegSettings(db)
    key = data.key
    value = data.value

    handlers = {
        "video_quality": settings.set_video_quality,
        "video_codec": settings.set_video_codec,
        "video_preset": settings.set_video_preset,
        "video_crf": settings.set_video_crf,
        "video_bitrate": settings.set_video_bitrate,
        "pixel_format": settings.set_pixel_format,
        "audio_codec": settings.set_audio_codec,
        "audio_bitrate": settings.set_audio_bitrate,
        "audio_sample_rate": settings.set_audio_sample_rate,
    }

    handler = handlers.get(key)
    if not handler:
        raise HTTPException(status_code=400, detail=f"Unknown FFmpeg video setting: '{key}'")

    handler(value)

    # If quality is changed, auto-apply the preset + CRF
    if key == "video_quality":
        settings.apply_quality_preset(value)

    return {"key": key, "value": value, "success": True}

@router.get("/{key}", response_model=SettingsResponse)
def get_setting(key: str, decrypt: bool = False, db: Session = Depends(get_db)):
    mgr = SettingsManager(db)
    value = mgr.get(key, decrypt_value=decrypt)
    if value is None:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    setting = db.query(Setting).filter(Setting.key == key).first()
    # If decrypt=true, return the decrypted value in the response
    if decrypt and setting and setting.is_encrypted:
        return SettingsResponse(
            key=setting.key,
            value=value,
            is_encrypted=setting.is_encrypted,
            updated_at=setting.updated_at,
        )
    return setting