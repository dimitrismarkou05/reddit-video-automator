"""Video generation and progress tracking routes."""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from core.database import get_db
from stories.models import Story, StoryStatus
from video.models import GeneratedVideo
from video.schemas import (
    VideoGenerationRequest,
    VideoGenerationResponse,
    GeneratedVideoResponse,
    VideoProgressResponse,
)
from services.notification_service import NotificationService
from video.engine.pipeline import VideoPipeline, VideoPipelineError

router = APIRouter()


@router.post("/generate", response_model=VideoGenerationResponse)
def generate_video(
    request: VideoGenerationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    story = db.query(Story).filter(Story.id == request.story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    if story.generated_video:
        raise HTTPException(status_code=400, detail="Video already generated for this story")

    story.status = StoryStatus.VIDEO_PROCESSING.value
    db.commit()
    NotificationService(db).create(
        "video", "info",
        f'Video generation started for "{story.title[:50]}..."',
        {"story_id": story.id},
    )

    background_tasks.add_task(_run_video_generation, db, request, story.id)

    return VideoGenerationResponse(
        video_id=0,
        status="processing",
        message="Video generation started in background",
    )


def _run_video_generation(db: Session, request: VideoGenerationRequest, story_id: int) -> None:
    from core.database import SessionLocal
    session = SessionLocal()
    try:
        pipe = VideoPipeline(session)
        story = session.query(Story).filter(Story.id == story_id).first()
        video = pipe.generate(
            story_id=request.story_id,
            include_updates=request.include_updates,
            tts_provider=request.tts_provider,
            tts_voice=request.tts_voice,
            background_source=request.background_source,
            video_format=request.video_format,
            subtitle_style=request.subtitle_style,
            generate_hashtags=request.generate_hashtags,
        )
        NotificationService(session).create(
            "video", "success",
            f'Video generation completed for "{story.title[:50]}..."',
            {"story_id": story.id, "video_id": video.id},
        )
    except Exception as exc:
        NotificationService(session).create(
            "video", "error",
            f"Video generation failed: {exc}",
            {"story_id": story_id, "error": str(exc)},
        )
    finally:
        session.close()


@router.get("", response_model=List[GeneratedVideoResponse])
def list_videos(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(GeneratedVideo)
    if status:
        q = q.filter(GeneratedVideo.status == status)
    return q.order_by(GeneratedVideo.created_at.desc()).all()


@router.get("/{video_id}", response_model=GeneratedVideoResponse)
def get_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.get("/{video_id}/progress", response_model=VideoProgressResponse)
def get_video_progress(video_id: int, db: Session = Depends(get_db)):
    video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    return VideoProgressResponse(
        video_id=video.id,
        status=video.status,
        progress_percent=video.progress_percent,
        current_step=video.status,
        error_message=video.error_message,
    )
