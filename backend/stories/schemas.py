from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Generic, TypeVar
from pydantic import BaseModel, ConfigDict, Field, field_serializer

T = TypeVar("T")


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
    updates: List["StoryResponse"] = []

    @field_serializer('created_utc', 'fetched_at')
    def serialize_datetime(self, value: datetime) -> str:
        if value is None:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


class StoryDetailResponse(StoryResponse):
    updates: List[StoryResponse] = []
    parent_story: Optional[StoryResponse] = None


class StoryChainResponse(BaseModel):
    original: StoryResponse
    updates: List[StoryResponse] = []


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""
    items: List[T]
    total: int
    page: int
    pages: int
    limit: int


class StoryListResponse(PaginatedResponse[StoryResponse]):
    """Paginated list of stories."""
    pass
