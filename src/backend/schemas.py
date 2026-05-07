from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, ConfigDict


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