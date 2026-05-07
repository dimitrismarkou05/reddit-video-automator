from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Optional, List

from sqlalchemy import String, Text, Integer, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class StoryStatus(str, PyEnum):
    FETCHED = "fetched"
    STORED = "stored"
    UPDATE_LINKED = "update_linked"
    READY_FOR_VIDEO = "ready_for_video"
    VIDEO_PROCESSING = "video_processing"
    VIDEO_DONE = "video_done"
    VIDEO_FAILED = "video_failed"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    UPLOAD_FAILED = "upload_failed"


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(primary_key=True)
    reddit_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(100), index=True)
    subreddit: Mapped[str] = mapped_column(String(100), index=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text)
    permalink: Mapped[str] = mapped_column(Text)
    created_utc: Mapped[datetime] = mapped_column(DateTime)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    status: Mapped[str] = mapped_column(
        String(50), default=StoryStatus.STORED.value
    )

    # Update linking (self-referential)
    parent_story_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("stories.id"), nullable=True, index=True
    )
    is_update: Mapped[bool] = mapped_column(Boolean, default=False)
    update_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    updates: Mapped[List["Story"]] = relationship(
        back_populates="parent_story",
        remote_side="Story.id",
        cascade="all, delete-orphan",
    )
    parent_story: Mapped[Optional["Story"]] = relationship(
        back_populates="updates",
        remote_side="Story.parent_story_id",
    )

    def __repr__(self) -> str:
        return f"<Story(id={self.id}, reddit_id={self.reddit_id}, title={self.title[:50]}...)>"


class Subreddit(Base):
    __tablename__ = "subreddits"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    added_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    fetch_settings: Mapped[dict] = mapped_column(JSON, default=dict)

    def __repr__(self) -> str:
        return f"<Subreddit(name={self.name})>"


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )