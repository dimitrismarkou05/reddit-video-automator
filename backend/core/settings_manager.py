from typing import Optional
from sqlalchemy.orm import Session

from settings.models import Setting
from core.crypto import encrypt, decrypt
import logging

logger = logging.getLogger(__name__)


class SettingsManager:
    def __init__(self, db: Session):
        self.db = db

    def get(self, key: str, default: Optional[str] = None, decrypt_value: bool = False) -> Optional[str]:
        setting = self.db.query(Setting).filter(Setting.key == key).first()
        if not setting:
            return default

        if decrypt_value and setting.is_encrypted:
            try:
                return decrypt(setting.value)
            except Exception as exc:
                logger.error(f"[SettingsManager] Decryption failed for key='{key}': {type(exc).__name__}: {exc}")
                # If decryption fails, return None so caller knows it's broken
                return None
        
        return setting.value

    def set(self, key: str, value: str, encrypt_value: bool = False) -> Setting:
        if encrypt_value:
            value = encrypt(value)

        setting = self.db.query(Setting).filter(Setting.key == key).first()
        if setting:
            setting.value = value
            setting.is_encrypted = encrypt_value
        else:
            setting = Setting(key=key, value=value, is_encrypted=encrypt_value)
            self.db.add(setting)

        self.db.commit()
        self.db.refresh(setting)
        return setting