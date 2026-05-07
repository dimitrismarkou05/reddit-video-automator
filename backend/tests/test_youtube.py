"""Unit tests for YouTube integration modules."""

import json
import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Setting, GeneratedVideo, Story, StoryStatus, VideoStatus
from youtube.auth import YouTubeAuthManager, YouTubeAuthError
from youtube.uploader import UploadMetadata, YouTubeUploader
from youtube.manager import YouTubeManager, VideoAnalytics


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# Auth tests
def test_auth_manager_not_configured(db):
    mgr = YouTubeAuthManager(db)
    assert mgr.is_configured() is False
    assert mgr.is_authenticated() is False


def test_auth_manager_configured_but_not_authenticated(db):
    mgr = YouTubeAuthManager(db)
    mgr.settings.set("youtube_client_id", "test-client-id", encrypt_value=True)
    mgr.settings.set("youtube_client_secret", "test-secret", encrypt_value=True)

    assert mgr.is_configured() is True
    assert mgr.is_authenticated() is False


def test_auth_state_generation(db):
    mgr = YouTubeAuthManager(db)
    mgr.settings.set("youtube_client_id", "test-client-id", encrypt_value=True)
    mgr.settings.set("youtube_client_secret", "test-secret", encrypt_value=True)

    flow = mgr.initiate_auth_flow(redirect_uri="http://localhost:9999/callback")
    assert "auth_url" in flow
    assert "state" in flow
    assert "redirect_uri" in flow
    assert flow["redirect_uri"] == "http://localhost:9999/callback"
    assert "accounts.google.com" in flow["auth_url"]


def test_auth_state_verification_failure(db):
    mgr = YouTubeAuthManager(db)
    mgr.settings.set("youtube_client_id", "test-client-id", encrypt_value=True)
    mgr.settings.set("youtube_client_secret", "test-secret", encrypt_value=True)

    mgr.initiate_auth_flow()

    with pytest.raises(YouTubeAuthError) as exc_info:
        mgr.exchange_code(code="fake-code", state="wrong-state")
    assert "Invalid OAuth state" in str(exc_info.value)


def test_auth_token_storage_and_load(db):
    mgr = YouTubeAuthManager(db)
    mgr.settings.set("youtube_client_id", "test-client-id", encrypt_value=True)
    mgr.settings.set("youtube_client_secret", "test-secret", encrypt_value=True)

    fake_tokens = {
        "access_token": "access_123",
        "refresh_token": "refresh_456",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "test-client-id",
        "client_secret": "test-secret",
        "scopes": ["https://www.googleapis.com/auth/youtube"],
        "expiry": datetime.now(timezone.utc).timestamp() + 3600,
        "token_type": "Bearer",
    }
    mgr._save_tokens(fake_tokens)

    loaded = mgr._load_tokens()
    assert loaded["access_token"] == "access_123"
    assert loaded["refresh_token"] == "refresh_456"


def test_auth_logout(db):
    mgr = YouTubeAuthManager(db)
    mgr.settings.set("youtube_client_id", "cid", encrypt_value=True)
    mgr.settings.set("youtube_client_secret", "secret", encrypt_value=True)
    mgr._save_tokens({"access_token": "tok", "refresh_token": "ref"})

    assert mgr.is_authenticated() is True
    mgr.logout()
    assert mgr.is_authenticated() is False


# Uploader tests (no real upload)
def test_upload_metadata_defaults():
    meta = UploadMetadata(title="Test Video")
    assert meta.title == "Test Video"
    assert meta.description == ""
    assert meta.tags == []
    assert meta.privacy_status == "private"
    assert meta.category_id == "22"


def test_upload_metadata_with_tags():
    meta = UploadMetadata(
        title="Test",
        description="A test video",
        tags=["reddit", "story"],
        privacy_status="public",
        category_id="24",
    )
    assert meta.tags == ["reddit", "story"]
    assert meta.privacy_status == "public"
    assert meta.category_id == "24"


# Manager dataclass tests
def test_video_analytics_dataclass():
    analytics = VideoAnalytics(
        video_id="abc123",
        title="Test",
        description="Desc",
        tags=["tag1"],
        views=100,
        likes=10,
        comments=5,
        duration="PT2M30S",
        thumbnail_url="http://example.com/thumb.jpg",
        privacy_status="public",
        upload_date="2024-01-01T00:00:00Z",
        category_id="22",
    )
    assert analytics.video_id == "abc123"
    assert analytics.views == 100
    assert analytics.privacy_status == "public"
