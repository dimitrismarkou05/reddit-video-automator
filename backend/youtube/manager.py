"""YouTube video management: analytics, metadata editing, deletion, privacy changes."""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from models import GeneratedVideo
from youtube.auth import YouTubeAuthManager, YouTubeAuthError


class YouTubeManagerError(Exception):
    """Raised when a management operation fails."""
    pass


@dataclass
class VideoAnalytics:
    """Flattened analytics + metadata snapshot for a YouTube video."""
    video_id: str
    title: str
    description: str
    tags: List[str]
    views: int
    likes: int
    comments: int
    duration: str
    thumbnail_url: str
    privacy_status: str
    upload_date: str
    category_id: str


class YouTubeManager:
    """CRUD + analytics for videos already on YouTube."""

    def __init__(self, db: Session):
        self.db = db
        self.auth = YouTubeAuthManager(db)

    def _get_service(self):
        return self.auth.build_service()

    def get_video_stats(self, youtube_video_id: str) -> VideoAnalytics:
        """Fetch full metadata + statistics for a single video."""
        service = self._get_service()

        try:
            response = service.videos().list(
                part="snippet,statistics,contentDetails,status",
                id=youtube_video_id,
            ).execute()
        except HttpError as exc:
            raise YouTubeManagerError(
                f"Failed to fetch video stats (HTTP {exc.resp.status}): {exc.content}"
            )

        items = response.get("items", [])
        if not items:
            raise YouTubeManagerError(f"Video {youtube_video_id} not found on YouTube.")

        item = items[0]
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        content = item.get("contentDetails", {})
        status = item.get("status", {})

        thumbs = snippet.get("thumbnails", {})
        thumb_url = (
            thumbs.get("maxres", {}).get("url")
            or thumbs.get("standard", {}).get("url")
            or thumbs.get("high", {}).get("url")
            or thumbs.get("medium", {}).get("url")
            or thumbs.get("default", {}).get("url")
            or ""
        )

        return VideoAnalytics(
            video_id=youtube_video_id,
            title=snippet.get("title", ""),
            description=snippet.get("description", ""),
            tags=snippet.get("tags", []),
            views=int(stats.get("viewCount", 0)),
            likes=int(stats.get("likeCount", 0)),
            comments=int(stats.get("commentCount", 0)),
            duration=content.get("duration", "PT0S"),
            thumbnail_url=thumb_url,
            privacy_status=status.get("privacyStatus", "unknown"),
            upload_date=snippet.get("publishedAt", ""),
            category_id=snippet.get("categoryId", "22"),
        )

    def get_channel_videos(
        self,
        max_results: int = 50,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List videos from the authenticated user's channel."""
        service = self._get_service()

        try:
            channels_resp = service.channels().list(
                part="contentDetails",
                mine=True,
            ).execute()
        except HttpError as exc:
            raise YouTubeManagerError(
                f"Failed to fetch channel (HTTP {exc.resp.status}): {exc.content}"
            )

        items = channels_resp.get("items", [])
        if not items:
            raise YouTubeManagerError("No YouTube channel found for this account.")

        uploads_playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

        playlist_resp = service.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=max_results,
            pageToken=page_token,
        ).execute()

        videos = []
        for item in playlist_resp.get("items", []):
            snippet = item.get("snippet", {})
            content = item.get("contentDetails", {})
            videos.append({
                "youtube_video_id": content.get("videoId"),
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "published_at": snippet.get("publishedAt", ""),
                "thumbnail_url": (
                    snippet.get("thumbnails", {}).get("medium", {}).get("url", "")
                ),
            })

        return {
            "videos": videos,
            "next_page_token": playlist_resp.get("nextPageToken"),
            "total_results": playlist_resp.get("pageInfo", {}).get("totalResults", 0),
        }

    def update_video_metadata(
        self,
        youtube_video_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        category_id: Optional[str] = None,
    ) -> VideoAnalytics:
        """Update snippet-level metadata for a video. Returns refreshed stats."""
        service = self._get_service()

        current = self.get_video_stats(youtube_video_id)

        snippet = {
            "title": title if title is not None else current.title,
            "description": description if description is not None else current.description,
            "tags": tags if tags is not None else current.tags,
            "categoryId": category_id if category_id is not None else current.category_id,
        }

        body = {"id": youtube_video_id, "snippet": snippet}

        try:
            service.videos().update(
                part="snippet",
                body=body,
            ).execute()
        except HttpError as exc:
            raise YouTubeManagerError(
                f"Failed to update metadata (HTTP {exc.resp.status}): {exc.content}"
            )

        return self.get_video_stats(youtube_video_id)

    def update_privacy_status(
        self,
        youtube_video_id: str,
        privacy_status: str,
    ) -> VideoAnalytics:
        """Change the privacy status of a video. Returns refreshed stats."""
        if privacy_status not in {"public", "private", "unlisted"}:
            raise YouTubeManagerError(
                f"Invalid privacy status: {privacy_status}. "
                "Must be one of: public, private, unlisted."
            )

        service = self._get_service()
        body = {
            "id": youtube_video_id,
            "status": {"privacyStatus": privacy_status},
        }

        try:
            service.videos().update(
                part="status",
                body=body,
            ).execute()
        except HttpError as exc:
            raise YouTubeManagerError(
                f"Failed to update privacy (HTTP {exc.resp.status}): {exc.content}"
            )

        local = (
            self.db.query(GeneratedVideo)
            .filter(GeneratedVideo.youtube_video_id == youtube_video_id)
            .first()
        )
        if local:
            local.youtube_upload_status = privacy_status
            self.db.commit()

        return self.get_video_stats(youtube_video_id)

    def delete_video(self, youtube_video_id: str) -> None:
        """Permanently delete a video from YouTube."""
        service = self._get_service()

        try:
            service.videos().delete(id=youtube_video_id).execute()
        except HttpError as exc:
            raise YouTubeManagerError(
                f"Failed to delete video (HTTP {exc.resp.status}): {exc.content}"
            )

        local = (
            self.db.query(GeneratedVideo)
            .filter(GeneratedVideo.youtube_video_id == youtube_video_id)
            .first()
        )
        if local:
            local.youtube_video_id = None
            local.youtube_upload_status = "not_uploaded"
            local.status = "done"
            self.db.commit()
