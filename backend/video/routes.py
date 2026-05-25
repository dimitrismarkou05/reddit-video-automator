"""Video generation API routes."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

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

router = APIRouter()


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


@router.post("/generate", response_model=VideoGenerationResponse)
def generate_video(
    request: VideoGenerationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    story = db.query(Story).filter(Story.id == request.story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    existing = db.query(GeneratedVideo).filter(
        GeneratedVideo.story_id == request.story_id
    ).first()
    if existing and existing.status not in (
        VideoStatus.FAILED.value,
        VideoStatus.CANCELLED.value,
    ):
        return VideoGenerationResponse(
            video_id=existing.id,
            status=existing.status,
            message="Video already exists for this story.",
            queue_position=existing.queue_position,
        )

    # FIX: Create video record without video_path/thumbnail_path (nullable now)
    # The pipeline sets these during execution
    video_record = GeneratedVideo(
        story_id=request.story_id,
        status=VideoStatus.QUEUED.value,
        format=request.video_format,
        background_source=request.background_source,
        subtitle_style=request.subtitle_style.model_dump() if request.subtitle_style else None,
    )
    db.add(video_record)
    db.commit()
    db.refresh(video_record)

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

    return VideoGenerationResponse(
        video_id=video_record.id,
        status=VideoStatus.QUEUED.value,
        message="Video generation queued.",
        queue_position=job_manager.queue_position(video_record.id),
    )


@router.get("/{video_id}/progress", response_model=VideoProgressResponse)
def get_progress(video_id: int, db: Session = Depends(get_db)):
    video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    return VideoProgressResponse(
        video_id=video.id,
        status=video.status,
        progress_percent=video.progress_percent,
        current_step=video.current_step,
        step_progress=video.step_progress,
        error_message=video.error_message,
        error_type=video.error_type,
        error_step=video.error_step,
        queue_position=video.queue_position,
        is_paused=video.is_paused,
    )


@router.post("/{video_id}/pause", response_model=VideoControlResponse)
def pause_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

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

    video.status = VideoStatus.CANCELLED.value
    video.cancelled_at = datetime.now(timezone.utc)
    db.commit()

    job_manager.cancel(video_id)

    return VideoControlResponse(
        success=True,
        status=video.status,
        message="Video generation cancelled.",
    )


@router.delete("/{video_id}")
def delete_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    db.delete(video)
    db.commit()
    return {"deleted": True, "video_id": video_id}
