from typing import Optional
from sqlalchemy.orm import Session

from backend.models import Setting
from backend.crypto import encrypt, decrypt


class SettingsManager:
    def __init__(self, db: Session):
        self.db = db

    def get(self, key: str, default: Optional[str] = None, decrypt_value: bool = False) -> Optional[str]:
        setting = self.db.query(Setting).filter(Setting.key == key).first()
        if not setting:
            return default

        if decrypt_value and setting.is_encrypted:
            return decrypt(setting.value)
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