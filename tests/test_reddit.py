"""Unit tests for reddit modules (no Reddit API calls)."""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, Story, Subreddit, StoryStatus
from backend.reddit.fetcher import sanitize_subreddit_name, StoryFetcher
from backend.reddit.linker import UpdateLinker


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_sanitize_subreddit_name():
    assert sanitize_subreddit_name("r/AskReddit") == "askreddit"
    assert sanitize_subreddit_name("https://reddit.com/r/AskReddit") == "askreddit"
    assert sanitize_subreddit_name("  AskReddit  ") == "askreddit"
    with pytest.raises(ValueError):
        sanitize_subreddit_name("invalid/name")


def test_add_subreddit(db):
    fetcher = StoryFetcher(db)
    sub = fetcher.add_subreddit("TestSubreddit")
    assert sub.name == "testsubreddit"
    assert sub.display_name == "r/testsubreddit"


def test_update_linking(db):
    # Seed original story
    original = Story(
        reddit_id="abc123",
        title="My crazy neighbor story",
        author="user1",
        subreddit="test",
        score=1000,
        url="http://example.com",
        permalink="/r/test/abc",
        created_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        status=StoryStatus.STORED.value,
    )
    db.add(original)
    db.commit()

    # Seed update
    update = Story(
        reddit_id="def456",
        title="UPDATE: My crazy neighbor story – part 2",
        author="user1",
        subreddit="test",
        score=500,
        url="http://example.com/2",
        permalink="/r/test/def",
        created_utc=datetime(2024, 1, 5, tzinfo=timezone.utc),
        status=StoryStatus.STORED.value,
    )
    db.add(update)
    db.commit()

    linker = UpdateLinker(db)
    linked = linker.link_updates_for_subreddit("test")

    assert linked == 1
    assert update.parent_story_id == original.id
    assert update.is_update is True

    chain = linker.get_story_chain(original.id)
    assert len(chain) == 2
    assert chain[0].reddit_id == "abc123"
    assert chain[1].reddit_id == "def456"