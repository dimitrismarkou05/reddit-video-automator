"""Video generation and progress tracking routes."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from core.database import get_db
from stories.models import Story, StoryStatus
from video.models import GeneratedVideo, VideoStatus
from video.schemas import (
    VideoGenerationRequest,
    VideoGenerationResponse,
    GeneratedVideoResponse,
    VideoProgressResponse,
    VideoControlResponse,
)
from services.notification_service import NotificationService
from video.engine.pipeline import VideoPipeline, VideoPipelineError
from video.engine.job_manager import job_manager

router = APIRouter()

# Active job status helpers
_ACTIVE_STATUSES = {
    VideoStatus.QUEUED.value,
    VideoStatus.PROCESSING.value,
    VideoStatus.TTS_DONE.value,
    VideoStatus.TRANSCRIBE_DONE.value,
    VideoStatus.SUBTITLES_DONE.value,
    VideoStatus.COMPOSITING_DONE.value,
    VideoStatus.PAUSED.value,
}


def _get_chain_root_id(story: Story) -> int:
    root = story
    while root.parent_story_id is not None:
        root = root.parent_story
    return root.id


def _find_active_video_for_story(story: Story, db: Session) -> Optional[GeneratedVideo]:
    """Find an actively generating video for this story or its chain."""
    # Check if this story has an active video
    if story.generated_video and story.generated_video.status in _ACTIVE_STATUSES:
        return story.generated_video

    # Check chain siblings for active videos with include_updates
    chain_root_id = _get_chain_root_id(story)
    chain_stories = db.query(Story).filter(
        Story.id == chain_root_id
    ).all()

    if chain_stories:
        root = chain_stories[0]
        if root.generated_video and root.generated_video.status in _ACTIVE_STATUSES:
            return root.generated_video

        # Check all updates of the root
        for update in root.updates:
            if update.generated_video and update.generated_video.status in _ACTIVE_STATUSES:
                return update.generated_video

    return None


@router.post("/generate", response_model=VideoGenerationResponse)
def generate_video(
    request: VideoGenerationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    story = db.query(Story).filter(Story.id == request.story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    # Check for existing active generation on this story chain
    existing_video = _find_active_video_for_story(story, db)
    if existing_video:
        # If include_updates matches, return the existing video
        return VideoGenerationResponse(
            video_id=existing_video.id,
            status=existing_video.status,
            message="An active video generation already exists for this story. Reconnecting to progress.",
        )

    # Check for completed video
    if story.generated_video and story.generated_video.status == VideoStatus.DONE.value:
        raise HTTPException(status_code=400, detail="Video already generated for this story")

    # Create the video record IMMEDIATELY with real DB entry
    output_folder_name = f"{story.id}_{story.title[:40]}"
    video = GeneratedVideo(
        story_id=request.story_id,
        video_path=f"output/{output_folder_name}/video.mp4",
        thumbnail_path=f"output/{output_folder_name}/thumbnail.jpg",
        format=request.video_format,
        status=VideoStatus.QUEUED.value,
        progress_percent=0,
        current_step="queued",
        tts_voice=request.tts_voice,
        tts_provider=request.tts_provider,
        background_source=request.background_source,
        subtitle_style=request.subtitle_style.model_dump() if request.subtitle_style else {},
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    story.status = StoryStatus.VIDEO_QUEUED.value
    db.commit()

    NotificationService(db).create(
        "video", "info",
        f'Video generation started for "{story.title[:50]}..."',
        {"story_id": story.id, "video_id": video.id},
    )

    # Pass only video_id to background task
    background_tasks.add_task(_run_video_generation, video.id, request)

    return VideoGenerationResponse(
        video_id=video.id,
        status=VideoStatus.QUEUED.value,
        message="Video generation started in background",
    )


async def _run_video_generation_async(video_id: int, request: VideoGenerationRequest) -> None:
    """Async wrapper for video generation with proper session lifecycle."""
    from core.database import SessionLocal
    db = SessionLocal()
    try:
        video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
        if not video:
            return

        story = db.query(Story).filter(Story.id == video.story_id).first()
        if not story:
            return

        # Try to acquire a processing slot
        slot_acquired = await job_manager.acquire_slot(video_id, story.id, db)
        if not slot_acquired:
            # Queued - will be processed when slot opens
            NotificationService(db).create(
                "video", "info",
                f'Video generation queued for "{story.title[:50]}..."',
                {"story_id": story.id, "video_id": video_id,
                 "queue_position": video.queue_position},
            )
            return

        pipeline = VideoPipeline(db)
        story.status = StoryStatus.VIDEO_PROCESSING.value
        video.status = VideoStatus.PROCESSING.value
        db.commit()

        # Register with job manager
        task = asyncio.current_task()
        if task:
            job_manager.register_job(video_id, story.id, task)

        # Create progress callback that sends notifications at key steps
        def progress_callback(percent: int, step: str):
            if step in ("tts_done", "transcribe_done", "subtitles_done", "compositing", "done"):
                step_messages = {
                    "tts_done": "TTS complete",
                    "transcribe_done": "Transcription complete",
                    "subtitles_done": "Subtitles generated",
                    "compositing": "Video compositing",
                    "done": "Video complete!",
                }
                msg = step_messages.get(step, f"Step: {step}")
                notif_level = "success" if step == "done" else "info"
                try:
                    NotificationService(db).create(
                        "video", notif_level,
                        f'{msg} for "{story.title[:50]}..."',
                        {"story_id": story.id, "video_id": video_id,
                         "step": step, "progress": percent},
                    )
                except Exception:
                    pass

        await pipeline.generate(
            video_record=video,
            include_updates=request.include_updates,
            tts_provider=request.tts_provider,
            tts_voice=request.tts_voice,
            background_source=request.background_source,
            video_format=request.video_format,
            subtitle_style=request.subtitle_style,
            generate_hashtags=request.generate_hashtags,
            progress_callback=progress_callback,
        )

        NotificationService(db).create(
            "video", "success",
            f'Video generation completed for "{story.title[:50]}..."',
            {"story_id": story.id, "video_id": video.id},
        )

    except Exception as exc:
        try:
            video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
            if video:
                video.status = VideoStatus.FAILED.value
                video.error_message = str(exc)
                video.error_type = type(exc).__name__
            story = db.query(Story).filter(Story.id == request.story_id).first()
            if story:
                story.status = StoryStatus.VIDEO_FAILED.value
            db.commit()

            friendly = str(exc)
            if "TTS" in str(type(exc).__name__) or "tts" in str(exc).lower():
                friendly = f"Text-to-speech failed: {exc}"
            elif "FFmpeg" in str(type(exc).__name__) or "ffmpeg" in str(exc).lower():
                friendly = f"Video rendering failed: {exc}"

            NotificationService(db).create(
                "video", "error",
                f"Video generation failed: {friendly}",
                {"story_id": request.story_id, "video_id": video_id,
                 "error": str(exc), "error_type": type(exc).__name__},
            )
        except Exception:
            pass
    finally:
        try:
            video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
            if video:
                job_manager.release_slot(video_id, video.story_id, db)
        except Exception:
            pass
        db.close()


def _run_video_generation(video_id: int, request: VideoGenerationRequest) -> None:
    """Entry point for BackgroundTasks - runs the async function."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_run_video_generation_async(video_id, request))
        else:
            loop.run_until_complete(_run_video_generation_async(video_id, request))
    except RuntimeError:
        # No running loop - create new one
        asyncio.run(_run_video_generation_async(video_id, request))


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
    if video.status not in _ACTIVE_STATUSES:
        raise HTTPException(status_code=400, detail="Video is not in a pausable state")

    video.status = VideoStatus.PAUSED.value
    video.is_paused = True
    video.paused_at = datetime.now(timezone.utc)
    db.commit()

    job_manager.pause_job(video_id)

    return VideoControlResponse(
        success=True, status="paused", message="Video generation paused",
    )


@router.post("/{video_id}/resume", response_model=VideoControlResponse)
def resume_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.status != VideoStatus.PAUSED.value:
        raise HTTPException(status_code=400, detail="Video is not paused")

    video.status = VideoStatus.QUEUED.value
    video.is_paused = False
    video.resumed_at = datetime.now(timezone.utc)
    db.commit()

    job_manager.resume_job(video_id)

    # Trigger background resume
    from video.schemas import SubtitleStyle
    request = VideoGenerationRequest(
        story_id=video.story_id,
        include_updates=True,
        tts_provider=video.tts_provider or "openai",
        tts_voice=video.tts_voice or "alloy",
        background_source=video.background_source or "",
        video_format=video.format or "shorts",
        subtitle_style=SubtitleStyle(**(video.subtitle_style or {})),
        generate_hashtags=True,
    )

    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_run_video_generation_async(video_id, request))
        else:
            loop.run_until_complete(_run_video_generation_async(video_id, request))
    except RuntimeError:
        asyncio.run(_run_video_generation_async(video_id, request))

    return VideoControlResponse(
        success=True, status="resuming", message="Video generation resuming",
    )


@router.post("/{video_id}/cancel", response_model=VideoControlResponse)
def cancel_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    video.status = VideoStatus.CANCELLED.value
    video.cancelled_at = datetime.now(timezone.utc)
    db.commit()

    job_manager.cancel_job(video_id)

    # Clean up temp files
    from video.engine.utils import cleanup_temp
    cleanup_temp(video_id)

    # Update story status
    story = db.query(Story).filter(Story.id == video.story_id).first()
    if story:
        story.status = StoryStatus.VIDEO_CANCELLED.value
        db.commit()

    return VideoControlResponse(
        success=True, status="cancelled", message="Video generation cancelled",
    )


@router.delete("/{video_id}", response_model=VideoControlResponse)
def delete_video(video_id: int, db: Session = Depends(get_db)):
    """Delete a video: remove files from disk, delete DB record, reset story status."""
    video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # Delete video file
    if video.video_path and Path(video.video_path).exists():
        Path(video.video_path).unlink(missing_ok=True)

    # Delete thumbnail
    if video.thumbnail_path and Path(video.thumbnail_path).exists():
        Path(video.thumbnail_path).unlink(missing_ok=True)

    # Delete temp files
    from video.engine.utils import cleanup_temp
    cleanup_temp(video_id)

    # Delete audio temp if exists
    if video.tts_audio_path and Path(video.tts_audio_path).exists():
        Path(video.tts_audio_path).unlink(missing_ok=True)
    if video.subtitle_ass_path and Path(video.subtitle_ass_path).exists():
        Path(video.subtitle_ass_path).unlink(missing_ok=True)

    # Update story status back
    story = db.query(Story).filter(Story.id == video.story_id).first()
    if story:
        story.status = StoryStatus.UPDATE_LINKED.value

    db.delete(video)
    db.commit()

    return VideoControlResponse(
        success=True, status="deleted", message="Video deleted successfully",
    )
