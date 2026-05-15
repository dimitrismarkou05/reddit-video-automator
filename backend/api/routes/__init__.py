"""FastAPI API v1 routes package."""

from fastapi import APIRouter

from api.routes.subreddits import router as subreddits_router
from api.routes.stories import router as stories_router
from api.routes.videos import router as videos_router
from api.routes.youtube import router as youtube_router
from api.routes.notifications import router as notifications_router
from api.routes.settings import router as settings_router

router = APIRouter()
router.include_router(subreddits_router)
router.include_router(stories_router)
router.include_router(videos_router)
router.include_router(youtube_router)
router.include_router(notifications_router)
router.include_router(settings_router)

__all__ = ["router"]
