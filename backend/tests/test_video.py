"""Unit tests for video modules."""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Story, GeneratedVideo, StoryStatus, VideoStatus
from video.utils import sanitize_filename, get_output_folder, calculate_target_dimensions
from video.thumbnail import ThumbnailGenerator
from schemas import SubtitleStyle


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_sanitize_filename():
    assert sanitize_filename("Hello World!") == "Hello_World"
    assert sanitize_filename("r/AskReddit: A Story?") == "rAskReddit_A_Story"
    assert sanitize_filename("   ") == "untitled"


def test_calculate_target_dimensions():
    w, h = calculate_target_dimensions("shorts")
    assert w == 1080
    assert h == 1920

    w, h = calculate_target_dimensions("normal")
    assert w == 1920
    assert h == 1080


def test_subtitle_style_defaults():
    style = SubtitleStyle()
    assert style.position == "center"
    assert style.font_size == 48
    assert style.font_color == "#FFFFFF"


def test_thumbnail_generator(tmp_path):
    gen = ThumbnailGenerator(width=640, height=360)
    output = tmp_path / "test_thumb.jpg"

    result = gen.generate(
        title="Test Reddit Story Title",
        subreddit="AskReddit",
        output_path=output,
        score=15000,
    )

    assert result.exists()
    assert result.stat().st_size > 0


def test_story_status_transitions(db):
    story = Story(
        reddit_id="test123",
        title="Test Story",
        author="testuser",
        subreddit="test",
        score=100,
        url="http://example.com",
        permalink="/r/test/test123",
        created_utc=datetime.now(timezone.utc),
        status=StoryStatus.STORED.value,
    )
    db.add(story)
    db.commit()

    assert story.status == StoryStatus.STORED.value

    story.status = StoryStatus.VIDEO_PROCESSING.value
    db.commit()
    assert story.status == StoryStatus.VIDEO_PROCESSING.value

    story.status = StoryStatus.VIDEO_DONE.value
    db.commit()
    assert story.status == StoryStatus.VIDEO_DONE.value
