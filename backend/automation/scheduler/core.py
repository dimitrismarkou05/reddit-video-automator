"""Background scheduler for automation templates."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from automation.models import AutomationTemplate, TemplateStatus, TemplateRun
from stories.models import Story, StoryStatus
from video.models import GeneratedVideo
from subreddits.client.fetcher import StoryFetcher
from video.engine.pipeline import VideoPipeline, VideoPipelineError
from youtube.uploader import YouTubeUploader, UploadMetadata, YouTubeUploadError
from youtube.auth import YouTubeAuthManager
from core.settings_manager import SettingsManager
from notifications.sse import notification_queue

logger = logging.getLogger(__name__)


class TemplateScheduler:
    def __init__(self, db: Session):
        self.db = db
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("Template scheduler started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Template scheduler stopped")

    async def _scheduler_loop(self):
        while self._running:
            try:
                await self._process_templates()
            except Exception as exc:
                logger.error(f"Scheduler error: {exc}")
            await asyncio.sleep(60)

    async def _process_templates(self):
        now = datetime.now(timezone.utc)

        templates = self.db.query(AutomationTemplate).filter(
            AutomationTemplate.is_active == True,
            AutomationTemplate.status == TemplateStatus.ACTIVE.value,
        ).all()

        for template in templates:
            try:
                if template.schedule_type == "manual":
                    continue

                if template.next_run_at and template.next_run_at > now:
                    continue

                await self._execute_template(template)

                if template.schedule_type == "interval":
                    minutes = template.schedule_config.get("minutes", 60)
                    template.next_run_at = now + timedelta(minutes=minutes)

                self.db.commit()

            except Exception as exc:
                logger.error(f"Template {template.id} execution failed: {exc}")
                template.status = TemplateStatus.ERROR.value
                self.db.commit()

    async def _execute_template(self, template: AutomationTemplate):
        run = TemplateRun(template_id=template.id, status="running")
        self.db.add(run)
        self.db.commit()

        await notification_queue.broadcast(
            "automation",
            {"type": "started", "template_id": template.id, "run_id": run.id}
        )

        try:
            total_fetched = await self._fetch_stories(template)
            run.stories_fetched = total_fetched
            await notification_queue.broadcast(
                "automation",
                {"type": "fetch_complete", "template_id": template.id, "count": total_fetched}
            )

            if total_fetched > 0:
                videos_generated = await self._generate_videos(template, run)
                run.videos_generated = videos_generated
                await notification_queue.broadcast(
                    "automation",
                    {"type": "generation_complete", "template_id": template.id, "count": videos_generated}
                )

            if template.auto_upload and run.videos_generated > 0:
                videos_uploaded = await self._upload_videos(template, run)
                run.videos_uploaded = videos_uploaded
                await notification_queue.broadcast(
                    "automation",
                    {"type": "upload_complete", "template_id": template.id, "count": videos_uploaded}
                )

            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            template.last_run_at = datetime.now(timezone.utc)

            await notification_queue.broadcast(
                "automation",
                {"type": "completed", "template_id": template.id, "run_id": run.id}
            )

        except Exception as exc:
            run.status = "failed"
            run.errors = run.errors or []
            run.errors.append(str(exc))
            run.completed_at = datetime.now(timezone.utc)

            await notification_queue.broadcast(
                "automation",
                {"type": "failed", "template_id": template.id, "error": str(exc)}
            )

        self.db.commit()

    async def _fetch_stories(self, template: AutomationTemplate) -> int:
        fetcher = StoryFetcher(self.db)
        total_fetched = 0

        for sub_name in template.subreddit_names:
            sub = fetcher.add_subreddit(sub_name, template.fetch_settings)
            stories, _ = fetcher.fetch_stories(sub.id)
            total_fetched += len(stories)

        return total_fetched

    async def _generate_videos(self, template: AutomationTemplate, run: TemplateRun) -> int:
        stories = self.db.query(Story).filter(
            Story.subreddit.in_(template.subreddit_names),
            Story.status == StoryStatus.UPDATE_LINKED.value,
            Story.generated_video == None,
        ).all()

        count = 0
        for story in stories:
            try:
                pipeline = VideoPipeline(self.db)

                from video.schemas import SubtitleStyle
                style = SubtitleStyle(**template.subtitle_style) if template.subtitle_style else SubtitleStyle()

                video = pipeline.generate(
                    story_id=story.id,
                    include_updates=template.include_updates,
                    background_source=template.background_source,
                    video_format=template.video_format,
                    subtitle_style=style,
                    generate_hashtags=template.generate_hashtags,
                )
                count += 1
            except VideoPipelineError as exc:
                logger.error(f"Video generation failed for story {story.id}: {exc}")
                if run.errors is None:
                    run.errors = []
                run.errors.append(f"Story {story.id}: {exc}")

        return count

    async def _upload_videos(self, template: AutomationTemplate, run: TemplateRun) -> int:
        videos = self.db.query(GeneratedVideo).filter(
            GeneratedVideo.status == "done",
            GeneratedVideo.youtube_upload_status == "not_uploaded",
            GeneratedVideo.story.has(Story.subreddit.in_(template.subreddit_names)),
        ).all()

        auth = YouTubeAuthManager(self.db)
        if not auth.is_authenticated():
            logger.warning("YouTube not authenticated, skipping auto-upload")
            return 0

        count = 0
        uploader = YouTubeUploader(self.db)

        for video in videos:
            try:
                story = video.story
                title = template.youtube_title_template.replace("{story_title}", story.title)
                desc = template.youtube_description_template.replace("{story_title}", story.title)

                meta = UploadMetadata(
                    title=title,
                    description=desc,
                    tags=template.youtube_tags,
                    category_id=template.youtube_category,
                    privacy_status=template.youtube_privacy,
                )

                yt_id = uploader.upload_video(
                    video_path=video.video_path,
                    metadata=meta,
                    video_record_id=video.id,
                )

                video.youtube_video_id = yt_id
                video.youtube_upload_status = "uploaded"
                video.status = StoryStatus.UPLOADED.value
                count += 1
            except YouTubeUploadError as exc:
                logger.error(f"Upload failed for video {video.id}: {exc}")
                if run.errors is None:
                    run.errors = []
                run.errors.append(f"Video {video.id}: {exc}")

        self.db.commit()
        return count


_scheduler: Optional[TemplateScheduler] = None


async def start_scheduler(db: Session):
    global _scheduler
    _scheduler = TemplateScheduler(db)
    await _scheduler.start()


async def stop_scheduler():
    global _scheduler
    if _scheduler:
        await _scheduler.stop()
        _scheduler = None