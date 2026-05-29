from datetime import datetime, timezone
from typing import Dict, Optional
from pydantic import BaseModel, field_serializer


class SettingsUpdate(BaseModel):
    key: str
    value: str
    encrypt: bool = False


class SettingsResponse(BaseModel):
    key: str
    value: str
    is_encrypted: bool
    updated_at: datetime

    @field_serializer('updated_at')
    def serialize_datetime(self, value: datetime) -> str:
        if value is None:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


class SettingsBulkResponse(BaseModel):
    settings: Dict[str, Optional[str]]