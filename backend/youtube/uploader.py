"""YouTube video upload with resumable upload and progress tracking."""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable, Dict, Any

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from sqlalchemy.orm import Session

from video.models import GeneratedVideo
from stories.models import StoryStatus
from youtube.auth import YouTubeAuthManager, YouTubeAuthError


class YouTubeUploadError(Exception):
    """Raised when a video upload fails irrecoverably."""
    pass


@dataclass
class UploadMetadata:
    """Metadata required for a YouTube video upload."""
    title: str
    description: str = ""
    tags: Optional[list] = None
    category_id: str = "22"  # People & Blogs
    privacy_status: str = "private"  # public | private | unlisted
    made_for_kids: bool = False

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class YouTubeUploader:
    """Handles resumable video + thumbnail uploads to YouTube."""

    RETRIABLE_STATUS_CODES = {500, 502, 503, 504}
    MAX_RETRIES = 10

    def __init__(self, db: Session):
        self.db = db
        self.auth = YouTubeAuthManager(db)

    def _get_service(self):
        """Build the YouTube API service object."""
        return self.auth.build_service()

    def upload_video(
        self,
        video_path: str,
        metadata: UploadMetadata,
        video_record_id: Optional[int] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> str:
        """Upload a video file to YouTube and return the YouTube video ID."""
        service = self._get_service()
        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=5 * 1024 * 1024,  # 5 MB chunks
        )

        body = {
            "snippet": {
                "title": metadata.title,
                "description": metadata.description,
                "tags": metadata.tags,
                "categoryId": metadata.category_id,
            },
            "status": {
                "privacyStatus": metadata.privacy_status,
                "selfDeclaredMadeForKids": metadata.made_for_kids,
            },
        }

        request = service.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media,
        )

        response = None
        error = None
        retry = 0

        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    percent = int(status.progress() * 100)
                    self._report_progress(
                        video_record_id, percent, "uploading", progress_callback
                    )
            except HttpError as exc:
                if exc.resp.status in self.RETRIABLE_STATUS_CODES:
                    error = f"Retriable HTTP {exc.resp.status}: {exc.content}"
                else:
                    raise YouTubeUploadError(
                        f"Upload failed (HTTP {exc.resp.status}): {exc.content}"
                    )
            except Exception as exc:
                error = f"Retriable error: {exc}"

            if error:
                self._report_progress(
                    video_record_id, None, f"retry {retry + 1}: {error}", progress_callback
                )
                retry += 1
                if retry > self.MAX_RETRIES:
                    raise YouTubeUploadError(
                        f"Upload failed after {self.MAX_RETRIES} retries. Last error: {error}"
                    )
                time.sleep(min(2 ** retry, 60))
                error = None

        if "id" not in response:
            raise YouTubeUploadError(f"Unexpected upload response: {response}")

        video_id = response["id"]
        self._report_progress(
            video_record_id, 100, "upload complete", progress_callback
        )
        return video_id

    def upload_thumbnail(
        self,
        youtube_video_id: str,
        thumbnail_path: str,
    ) -> None:
        """Upload a custom thumbnail for an existing YouTube video."""
        service = self._get_service()
        media = MediaFileUpload(thumbnail_path, mimetype="image/jpeg")

        try:
            service.thumbnails().set(
                videoId=youtube_video_id,
                media_body=media,
            ).execute()
        except HttpError as exc:
            raise YouTubeUploadError(
                f"Thumbnail upload failed (HTTP {exc.resp.status}): {exc.content}"
            )

    def _report_progress(
        self,
        video_record_id: Optional[int],
        percent: Optional[int],
        step: str,
        callback: Optional[Callable[[int, str], None]],
    ) -> None:
        """Update DB record and invoke optional UI callback."""
        if video_record_id is not None:
            record = (
                self.db.query(GeneratedVideo)
                .filter(GeneratedVideo.id == video_record_id)
                .first()
            )
            if record:
                if percent is not None:
                    record.progress_percent = percent
                record.status = step
                if step == "upload complete":
                    record.youtube_upload_status = "uploaded"
                    record.status = "done"
                elif "retry" in step.lower():
                    record.youtube_upload_status = "uploading"
                self.db.commit()

        if callback and percent is not None:
            callback(percent, step)
