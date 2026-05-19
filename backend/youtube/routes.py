"""YouTube OAuth, upload, and management routes."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from core.database import get_db
from video.models import GeneratedVideo
from stories.models import StoryStatus
from youtube.schemas import (
    YouTubeAuthInitiateResponse,
    YouTubeAuthCallbackRequest,
    YouTubeAuthStatusResponse,
    YouTubeUploadRequest,
    YouTubeUploadResponse,
    YouTubeVideoStatsResponse,
    YouTubeUpdateMetadataRequest,
    YouTubeUpdatePrivacyRequest,
)
from services.notification_service import NotificationService
from services.error_service import ErrorService
from youtube.auth import YouTubeAuthManager, YouTubeAuthError
from youtube.uploader import YouTubeUploader, UploadMetadata, YouTubeUploadError
from youtube.manager import YouTubeManager, YouTubeManagerError
from youtube.template_loader import load_template, render_template

router = APIRouter()


@router.get("/auth/status", response_model=YouTubeAuthStatusResponse)
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


@router.post("/auth/initiate", response_model=YouTubeAuthInitiateResponse)
def youtube_auth_initiate(db: Session = Depends(get_db)):
    auth = YouTubeAuthManager(db)
    try:
        result = auth.initiate_auth_flow()
        return YouTubeAuthInitiateResponse(**result)
    except YouTubeAuthError as exc:
        raise ErrorService.to_http(exc, 400)


@router.get("/auth/callback")
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
        NotificationService(db).create(
            "upload", "success",
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


@router.post("/auth/callback")
def youtube_auth_callback(payload: YouTubeAuthCallbackRequest, db: Session = Depends(get_db)):
    auth = YouTubeAuthManager(db)
    try:
        auth.exchange_code(code=payload.code, state=payload.state)
        user_info = auth.get_user_info()
        NotificationService(db).create(
            "upload", "success",
            f"YouTube account connected: {user_info.get('email', 'Unknown')}",
            {"email": user_info.get("email"), "name": user_info.get("name")},
        )
        return {"success": True, "user": user_info}
    except YouTubeAuthError as exc:
        raise ErrorService.to_http(exc, 400)


@router.post("/auth/logout")
def youtube_auth_logout(db: Session = Depends(get_db)):
    auth = YouTubeAuthManager(db)
    try:
        auth.logout()
        NotificationService(db).create("upload", "info", "YouTube account disconnected")
        return {"success": True}
    except YouTubeAuthError as exc:
        raise ErrorService.to_http(exc, 400)


@router.post("/upload", response_model=YouTubeUploadResponse)
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

    NotificationService(db).create(
        "upload", "info",
        f'YouTube upload started for "{video_record.story.title[:50]}..."',
        {"video_id": video_record.id},
    )

    background_tasks.add_task(_run_youtube_upload, db, request)

    return YouTubeUploadResponse(
        youtube_video_id="",
        status="uploading",
        message="Upload started in background",
    )


def _run_youtube_upload(db: Session, request: YouTubeUploadRequest) -> None:
    from core.database import SessionLocal
    session = SessionLocal()
    try:
        uploader = YouTubeUploader(session)
        video_record = session.query(GeneratedVideo).filter(GeneratedVideo.id == request.video_id).first()

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
                NotificationService(session).create(
                    "upload", "warning",
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

        NotificationService(session).create(
            "upload", "success",
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
        NotificationService(session).create(
            "upload", "error",
            f"YouTube upload failed: {exc}",
            {"video_id": request.video_id, "error": str(exc)},
        )
    finally:
        session.close()


@router.get("/videos/{youtube_video_id}/stats", response_model=YouTubeVideoStatsResponse)
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
        raise ErrorService.to_http(exc, 400)


@router.put("/videos/{youtube_video_id}")
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
        NotificationService(db).create(
            "upload", "success",
            f'Updated metadata for "{stats.title[:50]}..."',
            {"youtube_video_id": youtube_video_id},
        )
        return {"success": True, "video": stats}
    except (YouTubeAuthError, YouTubeManagerError) as exc:
        raise ErrorService.to_http(exc, 400)


@router.put("/videos/{youtube_video_id}/privacy")
def youtube_update_privacy(
    youtube_video_id: str,
    payload: YouTubeUpdatePrivacyRequest,
    db: Session = Depends(get_db),
):
    manager = YouTubeManager(db)
    try:
        stats = manager.update_privacy_status(youtube_video_id, payload.privacy_status)
        NotificationService(db).create(
            "upload", "success",
            f'Privacy changed to {payload.privacy_status} for "{stats.title[:50]}..."',
            {"youtube_video_id": youtube_video_id, "privacy_status": payload.privacy_status},
        )
        return {"success": True, "privacy_status": stats.privacy_status}
    except (YouTubeAuthError, YouTubeManagerError) as exc:
        raise ErrorService.to_http(exc, 400)


@router.delete("/videos/{youtube_video_id}")
def youtube_delete_video(youtube_video_id: str, db: Session = Depends(get_db)):
    manager = YouTubeManager(db)
    try:
        manager.delete_video(youtube_video_id)
        NotificationService(db).create(
            "upload", "success",
            "Video deleted from YouTube",
            {"youtube_video_id": youtube_video_id},
        )
        return {"success": True, "deleted": True}
    except (YouTubeAuthError, YouTubeManagerError) as exc:
        raise ErrorService.to_http(exc, 400)
