"""Settings management routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from settings.models import Setting
from settings.schemas import SettingsUpdate, SettingsResponse
from core.settings_manager import SettingsManager

router = APIRouter()


@router.post("", response_model=SettingsResponse)
def set_setting(data: SettingsUpdate, db: Session = Depends(get_db)):
    mgr = SettingsManager(db)
    setting = mgr.set(data.key, data.value, encrypt_value=data.encrypt)
    return setting


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
