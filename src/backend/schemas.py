from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, ConfigDict, Field


class SubredditCreate(BaseModel):
    name: str
    fetch_settings: Optional[Dict[str, Any]] = None


class SubredditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    display_name: str
    is_active: bool
    fetch_settings: Dict[str, Any]
    added_at: datetime


class StoryBase(BaseModel):
    reddit_id: str
    title: str
    author: str
    subreddit: str
    score: int
    body: Optional[str] = None
    url: str
    permalink: str
    created_utc: datetime
    status: str
    is_update: bool = False
    update_reason: Optional[str] = None


class StoryResponse(StoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fetched_at: datetime
    parent_story_id: Optional[int] = None


class StoryDetailResponse(StoryResponse):
    updates: List[StoryResponse] = []
    parent_story: Optional[StoryResponse] = None


class StoryChainResponse(BaseModel):
    original: StoryResponse
    updates: List[StoryResponse] = []


class FetchResult(BaseModel):
    subreddit: str
    fetched_count: int
    error: Optional[str] = None


class SettingsUpdate(BaseModel):
    key: str
    value: str
    encrypt: bool = False


class SettingsResponse(BaseModel):
    key: str
    value: str
    is_encrypted: bool
    updated_at: datetime


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
    created_at: datetime
    completed_at: Optional[datetime]


class VideoProgressResponse(BaseModel):
    video_id: int
    status: str
    progress_percent: int
    current_step: str
    error_message: Optional[str]
