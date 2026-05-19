from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, field_serializer


class SubtitleStyle(BaseModel):
    position: str = "center"
    font_size: int = 48
    font_color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline_width: int = 2
    max_width_percent: int = 90


class VideoGenerationRequest(BaseModel):
    story_id: int
    include_updates: bool = True
    tts_provider: str = "openai"
    tts_voice: str = "alloy"
    background_source: str
    video_format: str = "shorts"
    subtitle_style: SubtitleStyle = Field(default_factory=SubtitleStyle)
    generate_hashtags: bool = True


class VideoGenerationResponse(BaseModel):
    video_id: int
    status: str
    message: str


class GeneratedVideoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    story_id: int
    video_path: str
    thumbnail_path: str
    format: str
    duration_seconds: Optional[float]
    status: str
    progress_percent: int
    error_message: Optional[str]
    tts_voice: Optional[str]
    youtube_upload_status: str
    youtube_video_id: Optional[str]
    youtube_analytics: Optional[dict]
    created_at: datetime
    completed_at: Optional[datetime]

    @field_serializer('created_at', 'completed_at')
    def serialize_datetime(self, value: Optional[datetime]) -> str:
        if value is None:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


class VideoProgressResponse(BaseModel):
    video_id: int
    status: str
    progress_percent: int
    current_step: str
    error_message: Optional[str]
