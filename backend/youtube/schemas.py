from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, field_serializer


class YouTubeAuthInitiateResponse(BaseModel):
    auth_url: str
    state: str
    redirect_uri: str


class YouTubeAuthCallbackRequest(BaseModel):
    code: str
    state: str


class YouTubeAuthStatusResponse(BaseModel):
    is_configured: bool
    is_authenticated: bool
    user_info: Optional[Dict[str, Any]] = None


class YouTubeUploadRequest(BaseModel):
    video_id: int
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    category_id: str = "22"
    privacy_status: str = "private"
    upload_thumbnail: bool = True


class YouTubeUploadResponse(BaseModel):
    youtube_video_id: str
    status: str
    message: str


class YouTubeVideoStatsResponse(BaseModel):
    video_id: str
    title: str
    description: str
    tags: List[str]
    views: int
    likes: int
    comments: int
    duration: str
    thumbnail_url: str
    privacy_status: str
    upload_date: str
    category_id: str


class YouTubeUpdateMetadataRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    category_id: Optional[str] = None


class YouTubeUpdatePrivacyRequest(BaseModel):
    privacy_status: str
