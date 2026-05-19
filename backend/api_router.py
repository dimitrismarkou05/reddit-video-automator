"""Centralized API router orchestrator."""

from fastapi import APIRouter

from subreddits.routes import router as subreddits_router, fetch_router as subreddits_fetch_router
from stories.routes import router as stories_router
from video.routes import router as video_router
from video.sse import router as video_sse_router
from youtube.routes import router as youtube_router
from notifications.routes import router as notifications_router
from notifications.sse import router as notifications_sse_router
from settings.routes import router as settings_router
from automation.routes import router as automation_router

api_router = APIRouter()

# Subreddits
api_router.include_router(subreddits_router, prefix="/subreddits", tags=["Subreddits"])
api_router.include_router(subreddits_fetch_router, prefix="", tags=["Subreddits"])

# Stories
api_router.include_router(stories_router, prefix="/stories", tags=["Stories"])

# Videos
api_router.include_router(video_router, prefix="/videos", tags=["Videos"])

# SSE streams
api_router.include_router(video_sse_router, prefix="/sse", tags=["SSE"])
api_router.include_router(notifications_sse_router, prefix="/sse", tags=["SSE"])

# YouTube
api_router.include_router(youtube_router, prefix="/youtube", tags=["YouTube"])

# Notifications
api_router.include_router(notifications_router, prefix="/notifications", tags=["Notifications"])

# Settings
api_router.include_router(settings_router, prefix="/settings", tags=["Settings"])

# Automation
api_router.include_router(automation_router, prefix="/automation", tags=["Automation"])
