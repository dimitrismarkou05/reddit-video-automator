"""Video generation API routes with robust error handling and cleanup."""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from core.database import get_db
from video.schemas import (
    VideoGenerationRequest,
    VideoGenerationResponse,
    VideoProgressResponse,
    VideoControlResponse,
    GeneratedVideoResponse,
)
from video.models import GeneratedVideo, VideoStatus
from stories.models import Story
from video.engine.job_manager import job_manager
from video.engine.utils import cleanup_temp, select_background_video

logger = logging.getLogger(__name__)
router = APIRouter()


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
    query = db.query(GeneratedVideo)
    if status:
        query = query.filter(GeneratedVideo.status == status)
    videos = query.order_by(GeneratedVideo.created_at.desc()).all()
    return videos


@router.get("/{video_id}", response_model=GeneratedVideoResponse)
def get_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.post("/validate-background")
def validate_background(data: dict, db: Session = Depends(get_db)):
    """Validate a background video source before submission."""
    source = data.get("background_source", "")
    if not source:
        return {"valid": False, "error": "No background source provided"}
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

    return VideoProgressResponse(
        video_id=video.id,
        status=video.status,
        progress_percent=video.progress_percent,
        current_step=video.current_step,
        step_progress=video.step_progress,
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

    if video.status in (VideoStatus.DONE.value, VideoStatus.CANCELLED.value):
        return VideoControlResponse(
            success=False,
            status=video.status,
            message=f"Video already in {video.status} state.",
        )

    video.status = VideoStatus.CANCELLED.value
    video.cancelled_at = datetime.now(timezone.utc)
    video.queue_position = None
    db.commit()

    job_manager.cancel(video_id)

    return VideoControlResponse(
        success=True,
        status=video.status,
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

    # Cancel any active job first
    job_manager.cancel(video_id)
    job_manager.cleanup_job(video_id)

    db.delete(video)
    db.commit()
    return {"deleted": True, "video_id": video_id}
