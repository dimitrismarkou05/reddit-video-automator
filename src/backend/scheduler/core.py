"""Background scheduler for automation templates."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from backend.automation.models import AutomationTemplate, TemplateStatus, TemplateRun
from backend.reddit.fetcher import StoryFetcher
from backend.video.pipeline import VideoPipeline, VideoPipelineError
from backend.youtube.uploader import YouTubeUploader, UploadMetadata, YouTubeUploadError
from backend.youtube.auth import YouTubeAuthManager
from backend.settings_manager import SettingsManager
from backend.api.sse import notification_queue

logger = logging.getLogger(__name__)


class TemplateScheduler:
    """Manages scheduled execution of automation templates."""

    def __init__(self, db: Session):
        self.db = db
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the scheduler loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("Template scheduler started")

    async def stop(self):
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Template scheduler stopped")

    async def _scheduler_loop(self):
        """Main scheduler loop - checks templates every 60 seconds."""
        while self._running:
            try:
                await self._process_templates()
            except Exception as exc:
                logger.error(f"Scheduler error: {exc}")
            await asyncio.sleep(60)

    async def _process_templates(self):
        """Process all active templates due for execution."""
        now = datetime.now(timezone.utc)

        templates = self.db.query(AutomationTemplate).filter(
            AutomationTemplate.is_active == True,
            AutomationTemplate.status == TemplateStatus.ACTIVE.value,
        ).all()

        for template in templates:
            try:
                if template.schedule_type == "manual":
                    continue  # Manual templates don't auto-run

                if template.next_run_at and template.next_run_at > now:
                    continue

                await self._execute_template(template)

                # Update next run time
                if template.schedule_type == "interval":
                    minutes = template.schedule_config.get("minutes", 60)
                    template.next_run_at = now + timedelta(minutes=minutes)

                self.db.commit()

            except Exception as exc:
                logger.error(f"Template {template.id} execution failed: {exc}")
                template.status = TemplateStatus.ERROR.value
                self.db.commit()

    async def _execute_template(self, template: AutomationTemplate):
        """Execute a single automation template."""
        run = TemplateRun(template_id=template.id, status="running")
        self.db.add(run)
        self.db.commit()

        await notification_queue.broadcast(
            "automation",
            {"type": "started", "template_id": template.id, "run_id": run.id}
        )

        try:
            # 1. Fetch stories from monitored subreddits
            fetcher = StoryFetcher(self.db)
            total_fetched = 0

            for sub_name in template.subreddit_names:
                sub = fetcher.add_subreddit(sub_name, template.fetch_settings)
                stories = fetcher.fetch_stories(sub.id)
                total_fetched += len(stories)

            run.stories_fetched = total_fetched

            await notification_queue.broadcast(
                "automation",
                {"type": "fetch_complete", "template_id": template.id, "count": total_fetched}
            )

            # 2. Generate videos for new stories
            if total_fetched > 0:
                videos_generated = await self._generate_videos_for_template(template, run)
                run.videos_generated = videos_generated

                await notification_queue.broadcast(
                    "automation",
                    {"type": "generation_complete", "template_id": template.id, "count": videos_generated}
                )

            # 3. Auto-upload to YouTube if enabled
            if template.auto_upload and run.videos_generated > 0:
                videos_uploaded = await self._upload_videos_for_template(template, run)
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

    async def _generate_videos_for_template(self, template: AutomationTemplate, run: TemplateRun) -> int:
        """Generate videos for stories ready for video generation."""
        from backend.models import Story, StoryStatus, GeneratedVideo

        stories = self.db.query(Story).filter(
            Story.subreddit.in_(template.subreddit_names),
            Story.status == StoryStatus.UPDATE_LINKED.value,
            Story.generated_video == None,
        ).all()

        count = 0
        for story in stories:
            try:
                pipeline = VideoPipeline(self.db)

                from backend.schemas import SubtitleStyle
                style = SubtitleStyle(**template.subtitle_style) if template.subtitle_style else SubtitleStyle()

                video = pipeline.generate(
                    story_id=story.id,
                    include_updates=template.include_updates,
                    tts_provider=template.tts_provider,
                    tts_voice=template.tts_voice,
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

    async def _upload_videos_for_template(self, template: AutomationTemplate, run: TemplateRun) -> int:
        """Upload generated videos to YouTube."""
        from backend.models import GeneratedVideo, StoryStatus

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


# Global scheduler instance
_scheduler: Optional[TemplateScheduler] = None

async def start_scheduler(db: Session):
    """Start the global scheduler."""
    global _scheduler
    _scheduler = TemplateScheduler(db)
    await _scheduler.start()

async def stop_scheduler():
    """Stop the global scheduler."""
    global _scheduler
    if _scheduler:
        await _scheduler.stop()
        _scheduler = None
