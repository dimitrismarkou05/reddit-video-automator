"""Automation template models and scheduler."""

from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Optional, Dict, Any

from sqlalchemy import String, Text, Integer, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class TemplateStatus(str, PyEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"


class AutomationTemplate(Base):
    __tablename__ = "automation_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(50), default=TemplateStatus.PAUSED.value)

    # Subreddit configuration
    subreddit_names: Mapped[list] = mapped_column(JSON, default=list)
    fetch_settings: Mapped[dict] = mapped_column(JSON, default=dict)

    # Video generation settings
    tts_provider: Mapped[str] = mapped_column(String(50), default="openai")
    tts_voice: Mapped[str] = mapped_column(String(100), default="alloy")
    background_source: Mapped[str] = mapped_column(Text, default="")
    video_format: Mapped[str] = mapped_column(String(20), default="shorts")
    subtitle_style: Mapped[dict] = mapped_column(JSON, default=dict)
    include_updates: Mapped[bool] = mapped_column(Boolean, default=True)
    generate_hashtags: Mapped[bool] = mapped_column(Boolean, default=True)

    # YouTube upload settings
    youtube_title_template: Mapped[str] = mapped_column(Text, default="{story_title}")
    youtube_description_template: Mapped[str] = mapped_column(Text, default="")
    youtube_tags: Mapped[list] = mapped_column(JSON, default=list)
    youtube_privacy: Mapped[str] = mapped_column(String(20), default="private")
    youtube_category: Mapped[str] = mapped_column(String(20), default="22")
    auto_upload: Mapped[bool] = mapped_column(Boolean, default=True)

    # Schedule
    schedule_type: Mapped[str] = mapped_column(String(50), default="manual")  # manual, interval, cron
    schedule_config: Mapped[dict] = mapped_column(JSON, default=dict)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    runs: Mapped[list["TemplateRun"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by=lambda: TemplateRun.started_at.desc(),
    )


class TemplateRun(Base):
    __tablename__ = "template_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("automation_templates.id"))

    status: Mapped[str] = mapped_column(String(50), default="running")  # running, completed, failed
    stories_fetched: Mapped[int] = mapped_column(Integer, default=0)
    videos_generated: Mapped[int] = mapped_column(Integer, default=0)
    videos_uploaded: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    template: Mapped["AutomationTemplate"] = relationship(back_populates="runs")
