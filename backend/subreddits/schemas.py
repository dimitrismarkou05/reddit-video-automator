from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, field_serializer


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

    @field_serializer('added_at')
    def serialize_datetime(self, value: datetime) -> str:
        if value is None:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


class FetchRequest(BaseModel):
    """Request body for fetching stories with configurable parameters."""
    subreddit_id: Optional[int] = None  # None means fetch from all subreddits
    sort: str = "top"  # "top" | "new"
    time_filter: str = "week"  # "day" | "week" | "month" | "year" | "all"
    limit: int = 25  # 5, 10, 15, 20, 25


class FetchResult(BaseModel):
    subreddit: str
    fetched_count: int
    error: Optional[str] = None
