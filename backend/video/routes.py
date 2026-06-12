"""Video generation API routes with robust error handling and cleanup."""

import asyncio
import logging
import shutil
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from core.database import get_db
from core.config import TEMP_DIR, OUTPUT_DIR
from video.schemas import (
    VideoGenerationRequest,
    VideoGenerationResponse,
    VideoProgressResponse,
    VideoControlResponse,
    GeneratedVideoResponse,
)
from video.models import GeneratedVideo, VideoStatus
from stories.models import Story, StoryStatus
from video.engine.job_manager import job_manager
from video.engine.utils import cleanup_temp, cleanup_video_assets, select_background_video
import video.engine.progress_push as progress_push
from video.engine.progress_broadcaster import build_deleted_progress_payload
from notifications.sse import notification_queue

logger = logging.getLogger(__name__)
router = APIRouter()

# Set from main lifespan so sync routes can schedule coroutines on the app loop.
_app_loop: Optional[asyncio.AbstractEventLoop] = None


def set_app_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _app_loop
    _app_loop = loop


def _schedule_broadcast(event_type: str, data: dict) -> None:
    """Fire-and-forget SSE notification from a sync route."""
    async def _send() -> None:
        try:
            await notification_queue.broadcast(event_type, data)
        except Exception as exc:
            logger.warning(f"[VideoRoutes] Broadcast {event_type} failed: {exc}")

    loop = _app_loop
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                f"[VideoRoutes] No app event loop; skipping broadcast {event_type}"
            )
            return

    if loop.is_running():
        asyncio.run_coroutine_threadsafe(_send(), loop)
    else:
        loop.run_until_complete(_send())


def _video_to_response(video: GeneratedVideo, story: Story | None = None) -> GeneratedVideoResponse:
    """Build API response with optional joined story fields."""
    resp = GeneratedVideoResponse.model_validate(video)
    if story is not None:
        resp.story_title = story.title
        resp.story_subreddit = story.subreddit
    elif video.story is not None:
        resp.story_title = video.story.title
        resp.story_subreddit = video.story.subreddit
    return resp


def _get_story_chain_root(story: Story, db: Session) -> Story:
    """Get the root story of a chain (parent of all updates)."""
    root = story
    while root.parent_story_id is not None:
        parent = db.query(Story).filter(Story.id == root.parent_story_id).first()
        if not parent:
            break
        root = parent
    return root


@router.get("", response_model=list[GeneratedVideoResponse])
def list_videos(status: str | None = None, db: Session = Depends(get_db)):
    query = (
        db.query(GeneratedVideo, Story)
        .join(Story, GeneratedVideo.story_id == Story.id)
    )
    if status:
        query = query.filter(GeneratedVideo.status == status)
    rows = query.order_by(GeneratedVideo.created_at.desc()).all()
    return [_video_to_response(video, story) for video, story in rows]


@router.get("/{video_id}", response_model=GeneratedVideoResponse)
def get_video(video_id: int, db: Session = Depends(get_db)):
    row = (
        db.query(GeneratedVideo, Story)
        .join(Story, GeneratedVideo.story_id == Story.id)
        .filter(GeneratedVideo.id == video_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Video not found")
    video, story = row
    return _video_to_response(video, story)


def _resolve_thumbnail_path(video: GeneratedVideo) -> Path | None:
    """Locate thumbnail file from stored path or output folder fallback."""
    if video.thumbnail_path:
        candidate = Path(video.thumbnail_path)
        if candidate.is_file():
            return candidate

    if video.story_id:
        for folder in OUTPUT_DIR.glob(f"{video.story_id}_*"):
            candidate = folder / "thumbnail.jpg"
            if candidate.is_file():
                return candidate

    return None


@router.get("/{video_id}/thumbnail")
def get_video_thumbnail(video_id: int, db: Session = Depends(get_db)):
    video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    thumb_path = _resolve_thumbnail_path(video)
    if not thumb_path:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(thumb_path, media_type="image/jpeg")


@router.post("/upload-background")
async def upload_background(
    file: UploadFile = File(None),
    is_directory: bool = False,
    directory_files: list[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    """Upload background video(s) to server temp storage for browser mode."""
    upload_dir = TEMP_DIR / "uploaded_backgrounds"
    upload_dir.mkdir(parents=True, exist_ok=True)

    video_extensions = (".mp4", ".mov", ".avi", ".mkv", ".webm")

    if is_directory and directory_files:
        # Save all directory files
        saved_paths = []
        for f in directory_files:
            if not f.filename.lower().endswith(video_extensions):
                continue
            # Sanitize filename
            safe_name = Path(f.filename).name
            dest = upload_dir / safe_name
            with open(dest, "wb") as buffer:
                shutil.copyfileobj(f.file, buffer)
            saved_paths.append(str(dest))

        if not saved_paths:
            return {"valid": False, "error": "No valid video files in upload"}

        return {
            "valid": True,
            "path": str(upload_dir),
            "is_uploaded": True,
            "file_count": len(saved_paths),
        }

    elif file:
        # Single file upload
        if not file.filename.lower().endswith(video_extensions):
            return {"valid": False, "error": "File must be a video (.mp4, .mov, .avi, .mkv, .webm)"}

        safe_name = Path(file.filename).name
        dest = upload_dir / safe_name
        with open(dest, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return {
            "valid": True,
            "path": str(dest),
            "is_uploaded": True,
        }

    return {"valid": False, "error": "No file provided"}


@router.post("/validate-background")
def validate_background(data: dict, db: Session = Depends(get_db)):
    """Validate a background video source before submission."""
    source = data.get("background_source", "")
    if not source:
        return {"valid": False, "error": "No background source provided"}

    # Check if it's an uploaded path (in temp directory)
    uploaded_prefix = str(TEMP_DIR / "uploaded_backgrounds")
    if source.startswith(uploaded_prefix):
        path = Path(source)
        if path.exists():
            return {"valid": True}
        return {"valid": False, "error": "Uploaded files expired, please re-upload"}

    try:
        select_background_video(source)
        return {"valid": True}
    except ValueError as e:
        return {"valid": False, "error": str(e)}
    except Exception as e:
        logger.error(f"Background validation error: {e}")
        return {"valid": False, "error": f"Validation failed: {e}"}


@router.post("/generate", response_model=VideoGenerationResponse)
def generate_video(
    request: VideoGenerationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    story = db.query(Story).filter(Story.id == request.story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    # Find the root story for chain-based deduplication
    root_story = _get_story_chain_root(story, db)

    # Case 1: Check if this specific story already has an active generation
    existing = db.query(GeneratedVideo).filter(
        GeneratedVideo.story_id == request.story_id
    ).first()

    if existing and existing.status not in (
        VideoStatus.FAILED.value,
        VideoStatus.CANCELLED.value,
    ):
        # Story already has a generation in progress or done
        qpos = job_manager.queue_position(existing.id)
        return VideoGenerationResponse(
            video_id=existing.id,
            status=existing.status,
            message="Video already exists for this story.",
            queue_position=qpos,
        )

    # Case 2: If include_updates is True, check if parent story has active generation
    if request.include_updates and story.parent_story_id:
        parent_video = db.query(GeneratedVideo).filter(
            GeneratedVideo.story_id == root_story.id
        ).first()

        if parent_video and parent_video.status not in (
            VideoStatus.FAILED.value,
            VideoStatus.CANCELLED.value,
        ):
            # Parent generation exists - this update will be included
            qpos = job_manager.queue_position(parent_video.id)
            return VideoGenerationResponse(
                video_id=parent_video.id,
                status=parent_video.status,
                message="This update will be included in the parent story generation.",
                queue_position=qpos,
            )

    # Case 3: If include_updates is True and this is a root story,
    # check for any active child update generations
    if request.include_updates:
        child_ids = [u.id for u in root_story.updates] if hasattr(root_story, "updates") and root_story.updates else []
        if child_ids:
            child_videos = db.query(GeneratedVideo).filter(
                GeneratedVideo.story_id.in_(child_ids),
                GeneratedVideo.status.notin_([
                    VideoStatus.DONE.value,
                    VideoStatus.FAILED.value,
                    VideoStatus.CANCELLED.value,
                ])
            ).all()
            for cv in child_videos:
                job_manager.cleanup_job(cv.id)
                cv.status = VideoStatus.CANCELLED.value
                cv.cancelled_at = datetime.now(timezone.utc)
            if child_videos:
                db.commit()
                logger.info(f"Cancelled {len(child_videos)} child update generations for story {root_story.id}")

    # If there's a failed/cancelled record, reuse it
    if existing and existing.status in (VideoStatus.FAILED.value, VideoStatus.CANCELLED.value):
        # CRITICAL FIX: Clean up any stale job state first
        job_manager.cleanup_job(existing.id)

        # Reset the existing record for retry
        existing.status = VideoStatus.QUEUED.value
        existing.error_message = None
        existing.error_type = None
        existing.error_step = None
        existing.error_traceback = None
        existing.progress_percent = 0
        existing.current_step = "queued"
        existing.step_progress = 0
        existing.retry_count = existing.retry_count + 1
        existing.queue_position = None
        existing.cancelled_at = None
        existing.completed_at = None
        existing.is_paused = False
        existing.paused_at = None
        video_record = existing
        logger.info(f"Retrying video generation for story {request.story_id}, video_id={existing.id}")
    else:
        # Create new video record - FIX 1: Store all generation parameters
        video_record = GeneratedVideo(
            story_id=request.story_id,
            status=VideoStatus.QUEUED.value,
            format=request.video_format,
            background_source=request.background_source,
            subtitle_style=request.subtitle_style.model_dump() if request.subtitle_style else None,
            # FIX 1: Store generation parameters in DB for retry/resume
            voice_id=request.voice_id,
            include_updates=request.include_updates,
            generate_hashtags=request.generate_hashtags,
        )
        db.add(video_record)

    try:
        db.commit()
    except IntegrityError as exc:
        # FIX 5: Handle race condition - another request may have created the record
        db.rollback()
        logger.warning(f"IntegrityError during video generation for story {request.story_id}: {exc}")
        # Query the existing record
        existing = db.query(GeneratedVideo).filter(
            GeneratedVideo.story_id == request.story_id
        ).first()
        if existing:
            qpos = job_manager.queue_position(existing.id)
            return VideoGenerationResponse(
                video_id=existing.id,
                status=existing.status,
                message="Video already exists for this story.",
                queue_position=qpos,
            )
        raise HTTPException(status_code=500, detail="Failed to create video record due to concurrent request")

    db.refresh(video_record)

    logger.info(f"Submitting generation job: video_id={video_record.id}, story_id={request.story_id}")

    job_manager.submit(
        video_id=video_record.id,
        story_id=request.story_id,
        include_updates=request.include_updates,
        voice_id=request.voice_id,
        background_source=request.background_source,
        video_format=request.video_format,
        subtitle_style=request.subtitle_style,
        generate_hashtags=request.generate_hashtags,
    )

    qpos = job_manager.queue_position(video_record.id)

    # CRITICAL FIX: Different message for retry vs new generation
    is_retry = video_record.retry_count > 0
    message = "Video generation queued." if not is_retry else "Generation retry queued."

    return VideoGenerationResponse(
        video_id=video_record.id,
        status=VideoStatus.QUEUED.value,
        message=message,
        queue_position=qpos,
    )


@router.get("/{video_id}/progress", response_model=VideoProgressResponse)
def get_progress(video_id: int, db: Session = Depends(get_db)):
    video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    qpos = job_manager.queue_position(video_id)

    from video.engine.pipeline import _STEP_MESSAGES
    step = video.current_step or ""
    status_message = (
        video.status_message
        or _STEP_MESSAGES.get(step, step)
    )

    return VideoProgressResponse(
        video_id=video.id,
        status=video.status,
        progress_percent=video.progress_percent,
        current_step=video.current_step,
        step_progress=video.step_progress,
        status_message=status_message,
        error_message=video.error_message,
        error_type=video.error_type,
        error_step=video.error_step,
        queue_position=qpos or video.queue_position,
        is_paused=video.is_paused,
    )


@router.post("/{video_id}/pause", response_model=VideoControlResponse)
def pause_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.status in (VideoStatus.DONE.value, VideoStatus.FAILED.value, VideoStatus.CANCELLED.value):
        return VideoControlResponse(
            success=False,
            status=video.status,
            message=f"Cannot pause video in {video.status} state.",
        )

    video.status = VideoStatus.PAUSED.value
    video.is_paused = True
    video.paused_at = datetime.now(timezone.utc)
    db.commit()

    job_manager.pause(video_id)

    return VideoControlResponse(
        success=True,
        status=video.status,
        message="Video generation paused.",
    )


@router.post("/{video_id}/resume", response_model=VideoControlResponse)
def resume_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.status != VideoStatus.PAUSED.value:
        return VideoControlResponse(
            success=False,
            status=video.status,
            message=f"Cannot resume video in {video.status} state.",
        )

    video.status = VideoStatus.QUEUED.value
    video.is_paused = False
    video.resumed_at = datetime.now(timezone.utc)
    db.commit()

    job_manager.resume(video_id)

    return VideoControlResponse(
        success=True,
        status=video.status,
        message="Video generation resumed.",
    )


@router.post("/{video_id}/cancel", response_model=VideoControlResponse)
def cancel_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.status == VideoStatus.DONE.value:
        return VideoControlResponse(
            success=False,
            status=video.status,
            message=f"Video already in {video.status} state.",
        )

    story = db.query(Story).filter(Story.id == video.story_id).first()
    story_id = video.story_id
    story_title = story.title if story else ""

    # Signal cooperative cancel before hard-delete (pipeline checks DB status).
    if video.status not in (VideoStatus.CANCELLED.value,):
        video.status = VideoStatus.CANCELLED.value
        video.cancelled_at = datetime.now(timezone.utc)
        video.queue_position = None
        db.commit()

    job_manager.cancel(video_id)

    cleanup_video_assets(video, story_title)

    if story:
        story.status = StoryStatus.VIDEO_CANCELLED.value

    db.delete(video)
    db.commit()

    progress_push.push_progress(
        video_id, build_deleted_progress_payload(video_id)
    )
    _schedule_broadcast("video_deleted", {
        "video_id": video_id,
        "story_id": story_id,
    })

    return VideoControlResponse(
        success=True,
        status="deleted",
        message="Video generation cancelled.",
    )


@router.post("/{video_id}/retry", response_model=VideoGenerationResponse)
def retry_video(video_id: int, db: Session = Depends(get_db)):
    """Retry a failed or cancelled video generation."""
    video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.status not in (VideoStatus.FAILED.value, VideoStatus.CANCELLED.value):
        return VideoGenerationResponse(
            video_id=video.id,
            status=video.status,
            message=f"Cannot retry video in {video.status} state.",
        )

    # FIX 10: Clean up previous temp files before retry
    cleanup_temp(video_id)

    # Clean up old job state
    job_manager.cleanup_job(video_id)

    # Reset video record
    video.status = VideoStatus.QUEUED.value
    video.error_message = None
    video.error_type = None
    video.error_step = None
    video.error_traceback = None
    video.progress_percent = 0
    video.current_step = "queued"
    video.step_progress = 0
    video.retry_count = video.retry_count + 1
    video.queue_position = None
    video.cancelled_at = None
    video.is_paused = False
    video.paused_at = None
    db.commit()

    # FIX 1: Re-submit with original parameters from DB record
    from video.schemas import SubtitleStyle
    subtitle_style = None
    if video.subtitle_style:
        try:
            subtitle_style = SubtitleStyle(**video.subtitle_style)
        except Exception:
            subtitle_style = None

    job_manager.submit(
        video_id=video.id,
        story_id=video.story_id,
        include_updates=getattr(video, "include_updates", True),
        voice_id=getattr(video, "voice_id", "default"),
        background_source=video.background_source or "",
        video_format=video.format or "shorts",
        subtitle_style=subtitle_style,
        generate_hashtags=getattr(video, "generate_hashtags", True),
    )

    qpos = job_manager.queue_position(video.id)

    return VideoGenerationResponse(
        video_id=video.id,
        status=VideoStatus.QUEUED.value,
        message="Video generation retry queued.",
        queue_position=qpos,
    )


@router.delete("/{video_id}")
def delete_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    story = db.query(Story).filter(Story.id == video.story_id).first()
    story_title = story.title if story else ""

    story_id = video.story_id

    job_manager.cancel(video_id)
    job_manager.cleanup_job(video_id)
    cleanup_video_assets(video, story_title)

    if story:
        story.status = StoryStatus.READY_FOR_VIDEO.value

    db.delete(video)
    db.commit()

    progress_push.push_progress(
        video_id, build_deleted_progress_payload(video_id)
    )
    _schedule_broadcast("video_deleted", {
        "video_id": video_id,
        "story_id": story_id,
    })

    return {"deleted": True, "video_id": video_id}