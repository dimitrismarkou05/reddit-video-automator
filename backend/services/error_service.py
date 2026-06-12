"""Domain-to-HTTP error translation."""

from fastapi import HTTPException

from youtube.auth import YouTubeAuthError
from youtube.uploader import YouTubeUploadError
from youtube.manager import YouTubeManagerError
from video.engine.pipeline import VideoPipelineError, PipelineCancelledError, PipelinePausedError
from subreddits.client.client import RateLimitError


class ErrorService:
    """Converts domain exceptions to HTTPExceptions with appropriate status codes."""

    _STATUS_MAP = {
        (YouTubeAuthError, YouTubeUploadError, YouTubeManagerError, ValueError): 400,
        RateLimitError: 429,
    }

    @classmethod
    def to_http(cls, exc: Exception, default_status: int = 500) -> HTTPException:
        """Convert a domain exception to an HTTPException."""
        for exc_types, status in cls._STATUS_MAP.items():
            if isinstance(exc, exc_types):
                return HTTPException(status_code=status, detail=str(exc))
        return HTTPException(status_code=default_status, detail=f"Internal error: {exc}")
