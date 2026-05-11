"""FastAPI orchestration routes no business logic."""

import asyncio
from typing import List, Optional
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from database import get_db
from models import Subreddit, Story, Setting, GeneratedVideo, StoryStatus, Notification
from schemas import (
    SubredditCreate, SubredditResponse, StoryResponse, StoryDetailResponse,
    StoryChainResponse, FetchResult, SettingsUpdate, SettingsResponse,
    VideoGenerationRequest, VideoGenerationResponse, GeneratedVideoResponse,
    VideoProgressResponse, YouTubeAuthInitiateResponse, YouTubeAuthCallbackRequest,
    YouTubeAuthStatusResponse, YouTubeUploadRequest, YouTubeUploadResponse,
    YouTubeVideoStatsResponse, YouTubeUpdateMetadataRequest, YouTubeUpdatePrivacyRequest,
    NotificationResponse,
)
from reddit.fetcher import StoryFetcher
from reddit.linker import UpdateLinker
from reddit.client import RedditClient, RedditClientError
from settings_manager import SettingsManager
from video.pipeline import VideoPipeline, VideoPipelineError
from youtube.auth import YouTubeAuthManager, YouTubeAuthError
from youtube.uploader import YouTubeUploader, UploadMetadata, YouTubeUploadError
from youtube.manager import YouTubeManager, YouTubeManagerError
from api.sse import notification_queue
from api.template_loader import load_template, render_template
from automation.routes import router as automation_router

router = APIRouter()


def _handle_error(exc: Exception, default_status: int = 500) -> HTTPException:
    if isinstance(exc, (YouTubeAuthError, YouTubeUploadError, YouTubeManagerError)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, VideoPipelineError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=default_status, detail=f"Internal error: {exc}")


def _create_notification(
    db: Session, notif_type: str, level: str, message: str, details: Optional[dict] = None,
) -> None:
    """Create a notification and attempt SSE broadcast (best-effort)."""
    n = Notification(type=notif_type, level=level, message=message, details=details)
    db.add(n)
    db.commit()

    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            task = loop.create_task(notification_queue.broadcast("notification", {
                "id": n.id, "type": notif_type, "level": level, "message": message,
                "details": details, "is_read": False, "created_at": n.created_at.isoformat(),
            }))
            _ = task
    except RuntimeError:
        pass


router.include_router(automation_router, prefix="/automation", tags=["Automation"])


# Subreddits
@router.post("/subreddits", response_model=SubredditResponse, tags=["Subreddits"])
def add_subreddit(data: SubredditCreate, db: Session = Depends(get_db)):
    fetcher = StoryFetcher(db)
    try:
        return fetcher.add_subreddit(data.name, data.fetch_settings or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/subreddits", response_model=List[SubredditResponse], tags=["Subreddits"])
def list_subreddits(active_only: bool = False, db: Session = Depends(get_db)):
    q = db.query(Subreddit)
    if active_only:
        q = q.filter(Subreddit.is_active.is_(True))
    return q.all()


@router.delete("/subreddits/{subreddit_id}", tags=["Subreddits"])
def delete_subreddit(subreddit_id: int, db: Session = Depends(get_db)):
    sub = db.query(Subreddit).filter(Subreddit.id == subreddit_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subreddit not found")

    story_count = db.query(Story).filter(Story.subreddit == sub.name).delete()
    db.delete(sub)
    db.commit()

    _create_notification(
        db, "subreddit", "warning",
        f"Deleted r/{sub.name} and {story_count} associated stories",
        {"subreddit": sub.name, "deleted_stories": story_count},
    )
    return {"deleted": True, "subreddit": sub.name, "stories_deleted": story_count}


@router.delete("/subreddits", tags=["Subreddits"])
def delete_all_subreddits(db: Session = Depends(get_db)):
    subreddits = db.query(Subreddit).all()
    total_stories = 0
    for sub in subreddits:
        total_stories += db.query(Story).filter(Story.subreddit == sub.name).count()

    count = db.query(Subreddit).delete()
    db.query(Story).delete()
    db.commit()

    _create_notification(
        db, "subreddit", "warning",
        f"Deleted all {count} subreddits and {total_stories} stories",
        {"deleted_subreddits": count, "deleted_stories": total_stories},
    )
    return {"deleted": True, "count": count, "stories_deleted": total_stories}


@router.post("/subreddits/{subreddit_id}/fetch", response_model=FetchResult, tags=["Subreddits"])
def fetch_subreddit(subreddit_id: int, db: Session = Depends(get_db)):
    fetcher = StoryFetcher(db)
    sub = db.query(Subreddit).filter(Subreddit.id == subreddit_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subreddit not found")

    try:
        stories = fetcher.fetch_stories(subreddit_id)
        if len(stories) == 0:
            _create_notification(
                db, "story", "info",
                f"No new stories found in r/{sub.name} (all already fetched)",
                {"subreddit": sub.name, "count": 0},
            )
        else:
            _create_notification(
                db, "story", "success",
                f"Fetched {len(stories)} new stories from r/{sub.name}",
                {"subreddit": sub.name, "count": len(stories)},
            )
        return FetchResult(subreddit=sub.name, fetched_count=len(stories), error=None)
    except Exception as exc:
        _create_notification(
            db, "story", "error",
            f"Failed to fetch r/{sub.name}: {exc}",
            {"subreddit": sub.name},
        )
        return FetchResult(subreddit=sub.name, fetched_count=0, error=str(exc))


@router.post("/fetch-all", response_model=List[FetchResult], tags=["Subreddits"])
def fetch_all(db: Session = Depends(get_db)):
    fetcher = StoryFetcher(db)
    results, errors = fetcher.fetch_all_active()

    fetch_results = []
    for name, stories in results.items():
        error = errors.get(name)
        if error:
            _create_notification(
                db, "story", "error",
                f"Failed to fetch r/{name}: {error}",
                {"subreddit": name},
            )
        elif len(stories) == 0:
            _create_notification(
                db, "story", "info",
                f"No new stories found in r/{name} (all already fetched)",
                {"subreddit": name, "count": 0},
            )
        else:
            _create_notification(
                db, "story", "success",
                f"Fetched {len(stories)} new stories from r/{name}",
                {"subreddit": name, "count": len(stories)},
            )
        fetch_results.append(
            FetchResult(subreddit=name, fetched_count=len(stories), error=error)
        )

    return fetch_results


# Stories
@router.get("/stories", response_model=List[StoryResponse], tags=["Stories"])
def list_stories(
    subreddit: Optional[str] = None,
    status: Optional[str] = None,
    is_update: Optional[bool] = None,
    sort_by: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Story)
    if subreddit:
        q = q.filter(Story.subreddit == subreddit)
    if status:
        q = q.filter(Story.status == status)
    if is_update is not None:
        q = q.filter(Story.is_update == is_update)

    if sort_by == "date_asc":
        q = q.order_by(Story.created_utc.asc())
    elif sort_by == "score_desc":
        q = q.order_by(Story.score.desc())
    elif sort_by == "score_asc":
        q = q.order_by(Story.score.asc())
    elif sort_by == "title_asc":
        q = q.order_by(Story.title.asc())
    else:
        q = q.order_by(Story.created_utc.desc())

    return q.all()


@router.get("/stories/{story_id}", response_model=StoryDetailResponse, tags=["Stories"])
def get_story(story_id: int, db: Session = Depends(get_db)):
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@router.delete("/stories/{story_id}", tags=["Stories"])
def delete_story(story_id: int, db: Session = Depends(get_db)):
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    update_count = len(story.updates) if story.updates else 0
    title = story.title[:50]

    db.delete(story)
    db.commit()

    _create_notification(
        db, "story", "warning",
        f'Deleted story "{title}..." and {update_count} update(s)',
        {"story_id": story_id, "updates_deleted": update_count},
    )
    return {
        "deleted": True,
        "story_id": story_id,
        "title": title,
        "updates_deleted": update_count,
    }


@router.delete("/stories", tags=["Stories"])
def delete_all_stories(db: Session = Depends(get_db)):
    """Delete all stories (originals + updates) without touching subreddits."""
    count = db.query(Story).count()
    db.query(Story).delete()
    db.commit()

    _create_notification(
        db, "story", "warning",
        f"Deleted all {count} stories",
        {"deleted_count": count},
    )
    return {"deleted": True, "count": count}


@router.get("/stories/{story_id}/chain", response_model=StoryChainResponse, tags=["Stories"])
def get_story_chain(story_id: int, db: Session = Depends(get_db)):
    linker = UpdateLinker(db)
    chain = linker.get_story_chain(story_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Story not found")
    return StoryChainResponse(original=chain[0], updates=chain[1:])


@router.post("/stories/link-updates", tags=["Stories"])
def run_link_updates(subreddit: Optional[str] = None, db: Session = Depends(get_db)):
    linker = UpdateLinker(db)
    if subreddit:
        count = linker.link_updates_for_subreddit(subreddit)
    else:
        count = 0
        for (sub_name,) in db.query(Story.subreddit).distinct().all():
            count += linker.link_updates_for_subreddit(sub_name)
    _create_notification(
        db, "story", "success",
        f"Linked {count} update stories",
        {"linked_count": count},
    )
    return {"linked_count": count}


# Video Generation
@router.post("/videos/generate", response_model=VideoGenerationResponse, tags=["Videos"])
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
    _create_notification(
        db, "video", "info",
        f'Video generation started for "{story.title[:50]}..."',
        {"story_id": story.id},
    )

    def run_generation():
        from database import SessionLocal
        session = SessionLocal()
        try:
            pipe = VideoPipeline(session)
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
            _create_notification(
                session, "video", "success",
                f'Video generation completed for "{story.title[:50]}..."',
                {"story_id": story.id, "video_id": video.id},
            )
        except Exception as exc:
            _create_notification(
                session, "video", "error",
                f"Video generation failed: {exc}",
                {"story_id": story.id, "error": str(exc)},
            )
        finally:
            session.close()

    background_tasks.add_task(run_generation)

    return VideoGenerationResponse(
        video_id=0,
        status="processing",
        message="Video generation started in background",
    )


@router.get("/videos", response_model=List[GeneratedVideoResponse], tags=["Videos"])
def list_videos(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(GeneratedVideo)
    if status:
        q = q.filter(GeneratedVideo.status == status)
    return q.order_by(GeneratedVideo.created_at.desc()).all()


@router.get("/videos/{video_id}", response_model=GeneratedVideoResponse, tags=["Videos"])
def get_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.get("/videos/{video_id}/progress", response_model=VideoProgressResponse, tags=["Videos"])
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


# YouTube Auth
@router.get("/youtube/auth/status", response_model=YouTubeAuthStatusResponse, tags=["YouTube"])
def youtube_auth_status(db: Session = Depends(get_db)):
    auth = YouTubeAuthManager(db)
    user_info = None
    if auth.is_authenticated():
        try:
            user_info = auth.get_user_info()
        except YouTubeAuthError:
            pass
    return YouTubeAuthStatusResponse(
        is_configured=auth.is_configured(),
        is_authenticated=auth.is_authenticated(),
        user_info=user_info,
    )


@router.post("/youtube/auth/initiate", response_model=YouTubeAuthInitiateResponse, tags=["YouTube"])
def youtube_auth_initiate(db: Session = Depends(get_db)):
    auth = YouTubeAuthManager(db)
    try:
        result = auth.initiate_auth_flow()
        return YouTubeAuthInitiateResponse(**result)
    except YouTubeAuthError as exc:
        raise _handle_error(exc, 400)


@router.get("/youtube/auth/callback", tags=["YouTube"])
def youtube_auth_callback_get(
    code: str = None,
    state: str = None,
    db: Session = Depends(get_db),
):
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    auth = YouTubeAuthManager(db)
    try:
        auth.exchange_code(
            code=code, 
            state=state, 
            redirect_uri="http://localhost:8000/api/v1/youtube/auth/callback"
        )
        user_info = auth.get_user_info()
        _create_notification(
            db, "upload", "success",
            f"YouTube account connected: {user_info.get('email', 'Unknown')}",
            {"email": user_info.get("email"), "name": user_info.get("name")},
        )

        from fastapi.responses import HTMLResponse
        html_content = load_template("auth_callback.html")
        return HTMLResponse(content=html_content)

    except YouTubeAuthError as exc:
        from fastapi.responses import HTMLResponse
        html_content = render_template("auth_error.html", error_message=str(exc))
        return HTMLResponse(content=html_content, status_code=400)


@router.post("/youtube/auth/callback", tags=["YouTube"])
def youtube_auth_callback(payload: YouTubeAuthCallbackRequest, db: Session = Depends(get_db)):
    auth = YouTubeAuthManager(db)
    try:
        auth.exchange_code(code=payload.code, state=payload.state)
        user_info = auth.get_user_info()
        _create_notification(
            db, "upload", "success",
            f"YouTube account connected: {user_info.get('email', 'Unknown')}",
            {"email": user_info.get("email"), "name": user_info.get("name")},
        )
        return {"success": True, "user": user_info}
    except YouTubeAuthError as exc:
        raise _handle_error(exc, 400)


@router.post("/youtube/auth/logout", tags=["YouTube"])
def youtube_auth_logout(db: Session = Depends(get_db)):
    auth = YouTubeAuthManager(db)
    try:
        auth.logout()
        _create_notification(db, "upload", "info", "YouTube account disconnected")
        return {"success": True}
    except YouTubeAuthError as exc:
        raise _handle_error(exc, 400)


# YouTube Upload
@router.post("/youtube/upload", response_model=YouTubeUploadResponse, tags=["YouTube"])
def youtube_upload(
    request: YouTubeUploadRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    video_record = db.query(GeneratedVideo).filter(GeneratedVideo.id == request.video_id).first()
    if not video_record:
        raise HTTPException(status_code=404, detail="Video not found")

    if not Path(video_record.video_path).exists():
        raise HTTPException(status_code=400, detail="Video file not found on disk")

    video_record.status = StoryStatus.UPLOADING.value
    video_record.youtube_upload_status = "uploading"
    video_record.progress_percent = 0
    db.commit()

    _create_notification(
        db, "upload", "info",
        f'YouTube upload started for "{video_record.story.title[:50]}..."',
        {"video_id": video_record.id},
    )

    def run_upload():
        from database import SessionLocal
        session = SessionLocal()
        try:
            uploader = YouTubeUploader(session)

            meta = UploadMetadata(
                title=request.title or video_record.story.title,
                description=request.description or "",
                tags=request.tags or [],
                category_id=request.category_id,
                privacy_status=request.privacy_status,
            )

            def progress_cb(percent, step):
                rec = session.query(GeneratedVideo).filter(GeneratedVideo.id == request.video_id).first()
                if rec:
                    rec.progress_percent = percent
                    rec.status = step
                    session.commit()

            yt_id = uploader.upload_video(
                video_path=video_record.video_path,
                metadata=meta,
                video_record_id=request.video_id,
                progress_callback=progress_cb,
            )

            if request.upload_thumbnail and video_record.thumbnail_path and Path(video_record.thumbnail_path).exists():
                try:
                    uploader.upload_thumbnail(yt_id, video_record.thumbnail_path)
                except Exception as thumb_exc:
                    _create_notification(
                        session, "upload", "warning",
                        f"Thumbnail upload failed: {thumb_exc}",
                        {"video_id": request.video_id},
                    )

            rec = session.query(GeneratedVideo).filter(GeneratedVideo.id == request.video_id).first()
            if rec:
                rec.youtube_video_id = yt_id
                rec.youtube_upload_status = "uploaded"
                rec.status = StoryStatus.UPLOADED.value
                rec.progress_percent = 100
                session.commit()

            _create_notification(
                session, "upload", "success",
                f"Video uploaded to YouTube: {meta.title[:50]}...",
                {"video_id": request.video_id, "youtube_video_id": yt_id},
            )

        except Exception as exc:
            rec = session.query(GeneratedVideo).filter(GeneratedVideo.id == request.video_id).first()
            if rec:
                rec.youtube_upload_status = "upload_failed"
                rec.status = StoryStatus.UPLOAD_FAILED.value
                rec.error_message = str(exc)
                session.commit()
            _create_notification(
                session, "upload", "error",
                f"YouTube upload failed: {exc}",
                {"video_id": request.video_id, "error": str(exc)},
            )
        finally:
            session.close()

    background_tasks.add_task(run_upload)

    return YouTubeUploadResponse(
        youtube_video_id="",
        status="uploading",
        message="Upload started in background",
    )


# YouTube Management
@router.get("/youtube/videos/{youtube_video_id}/stats", response_model=YouTubeVideoStatsResponse, tags=["YouTube"])
def youtube_video_stats(youtube_video_id: str, db: Session = Depends(get_db)):
    manager = YouTubeManager(db)
    try:
        stats = manager.get_video_stats(youtube_video_id)
        local = (
            db.query(GeneratedVideo)
            .filter(GeneratedVideo.youtube_video_id == youtube_video_id)
            .first()
        )
        if local:
            local.youtube_analytics = {
                "views": stats.views,
                "likes": stats.likes,
                "comments": stats.comments,
                "privacy_status": stats.privacy_status,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            db.commit()
        return YouTubeVideoStatsResponse(
            video_id=stats.video_id,
            title=stats.title,
            description=stats.description,
            tags=stats.tags,
            views=stats.views,
            likes=stats.likes,
            comments=stats.comments,
            duration=stats.duration,
            thumbnail_url=stats.thumbnail_url,
            privacy_status=stats.privacy_status,
            upload_date=stats.upload_date,
            category_id=stats.category_id,
        )
    except (YouTubeAuthError, YouTubeManagerError) as exc:
        raise _handle_error(exc, 400)


@router.put("/youtube/videos/{youtube_video_id}", tags=["YouTube"])
def youtube_update_metadata(
    youtube_video_id: str,
    payload: YouTubeUpdateMetadataRequest,
    db: Session = Depends(get_db),
):
    manager = YouTubeManager(db)
    try:
        stats = manager.update_video_metadata(
            youtube_video_id=youtube_video_id,
            title=payload.title,
            description=payload.description,
            tags=payload.tags,
            category_id=payload.category_id,
        )
        _create_notification(
            db, "upload", "success",
            f'Updated metadata for "{stats.title[:50]}..."',
            {"youtube_video_id": youtube_video_id},
        )
        return {"success": True, "video": stats}
    except (YouTubeAuthError, YouTubeManagerError) as exc:
        raise _handle_error(exc, 400)


@router.put("/youtube/videos/{youtube_video_id}/privacy", tags=["YouTube"])
def youtube_update_privacy(
    youtube_video_id: str,
    payload: YouTubeUpdatePrivacyRequest,
    db: Session = Depends(get_db),
):
    manager = YouTubeManager(db)
    try:
        stats = manager.update_privacy_status(youtube_video_id, payload.privacy_status)
        _create_notification(
            db, "upload", "success",
            f'Privacy changed to {payload.privacy_status} for "{stats.title[:50]}..."',
            {"youtube_video_id": youtube_video_id, "privacy_status": payload.privacy_status},
        )
        return {"success": True, "privacy_status": stats.privacy_status}
    except (YouTubeAuthError, YouTubeManagerError) as exc:
        raise _handle_error(exc, 400)


@router.delete("/youtube/videos/{youtube_video_id}", tags=["YouTube"])
def youtube_delete_video(youtube_video_id: str, db: Session = Depends(get_db)):
    manager = YouTubeManager(db)
    try:
        manager.delete_video(youtube_video_id)
        _create_notification(
            db, "upload", "success",
            "Video deleted from YouTube",
            {"youtube_video_id": youtube_video_id},
        )
        return {"success": True, "deleted": True}
    except (YouTubeAuthError, YouTubeManagerError) as exc:
        raise _handle_error(exc, 400)


# Notifications
@router.get("/notifications", response_model=List[NotificationResponse], tags=["Notifications"])
def list_notifications(
    unread_only: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(Notification).order_by(Notification.created_at.desc())
    if unread_only:
        q = q.filter(Notification.is_read.is_(False))
    return q.limit(limit).all()


@router.post("/notifications/{notification_id}/read", tags=["Notifications"])
def mark_notification_read(notification_id: int, db: Session = Depends(get_db)):
    n = db.query(Notification).filter(Notification.id == notification_id).first()
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    n.is_read = True
    db.commit()
    return {"success": True}


@router.post("/notifications/read-all", tags=["Notifications"])
def mark_all_notifications_read(db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.is_read.is_(False)).update({"is_read": True})
    db.commit()
    return {"success": True}


@router.delete("/notifications/{notification_id}", tags=["Notifications"])
def delete_notification(notification_id: int, db: Session = Depends(get_db)):
    n = db.query(Notification).filter(Notification.id == notification_id).first()
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    db.delete(n)
    db.commit()
    return {"success": True}

@router.delete("/notifications", tags=["Notifications"])
def delete_all_notifications(db: Session = Depends(get_db)):
    count = db.query(Notification).delete()
    db.commit()
    return {"deleted": True, "count": count}

# Settings endpoints
@router.post("/settings", response_model=SettingsResponse, tags=["Settings"])
def set_setting(data: SettingsUpdate, db: Session = Depends(get_db)):
    mgr = SettingsManager(db)
    setting = mgr.set(data.key, data.value, encrypt_value=data.encrypt)
    return setting


@router.get("/settings/{key}", response_model=SettingsResponse, tags=["Settings"])
def get_setting(key: str, decrypt: bool = False, db: Session = Depends(get_db)):
    mgr = SettingsManager(db)
    value = mgr.get(key, decrypt_value=decrypt)
    if value is None:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    setting = db.query(Setting).filter(Setting.key == key).first()
    return setting