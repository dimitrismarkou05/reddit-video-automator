"""FFmpeg feature request/response schemas."""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class FfmpegStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ffmpeg_installed: bool
    ffprobe_installed: bool
    ffmpeg_path: Optional[str] = None
    ffprobe_path: Optional[str] = None
    ffmpeg_version: Optional[str] = None
    ffprobe_version: Optional[str] = None
    can_generate_videos: bool
    ffmpeg_in_path: bool = False


class SetPathRequest(BaseModel):
    ffmpeg_path: str
    ffprobe_path: Optional[str] = None


class CheckPathResponse(BaseModel):
    valid: bool
    ffmpeg_version: Optional[str] = None
    ffprobe_version: Optional[str] = None
    error: Optional[str] = None


class InstallRequest(BaseModel):
    force: bool = Field(default=False, description="Force re-install even if already present")


class InstallProgressEvent(BaseModel):
    event_type: str  # mirror_switch | retry | download_progress | extracting | installing | complete | failed | cancelled
    progress_percent: int = 0
    step: str = ""
    mirror: Optional[str] = None
    retry_count: int = 0
    error: Optional[str] = None
