import click
from rich.console import Console
from rich.table import Table
from sqlalchemy.orm import Session
from pathlib import Path

from backend.database import SessionLocal, init_db
from backend.models import Story, Subreddit, GeneratedVideo, StoryStatus, Notification
from backend.reddit.fetcher import StoryFetcher
from backend.reddit.linker import UpdateLinker
from backend.settings_manager import SettingsManager
from backend.video.pipeline import VideoPipeline, VideoPipelineError
from backend.video.utils import find_ffmpeg, get_ffmpeg_version
from backend.schemas import SubtitleStyle
from backend.youtube.auth import YouTubeAuthManager, YouTubeAuthError
from backend.youtube.uploader import YouTubeUploader, UploadMetadata, YouTubeUploadError
from backend.youtube.manager import YouTubeManager, YouTubeManagerError

console = Console()


@click.group()
def main():
    """Reddit Video Automator CLI"""
    init_db()


# Settings
@main.command("set-setting")
@click.argument("key")
@click.argument("value")
@click.option("--encrypt/--no-encrypt", default=False, help="Encrypt value at rest")
def set_setting(key, value, encrypt):
    """Store an application setting."""
    db = SessionLocal()
    try:
        mgr = SettingsManager(db)
        mgr.set(key, value, encrypt_value=encrypt)
        console.print(f"[green]Set[/green] {key} {'(encrypted)' if encrypt else ''}")
    finally:
        db.close()


@main.command("get-setting")
@click.argument("key")
@click.option("--decrypt/--no-decrypt", default=False, help="Decrypt if encrypted")
def get_setting(key, decrypt):
    """Read an application setting."""
    db = SessionLocal()
    try:
        mgr = SettingsManager(db)
        val = mgr.get(key, decrypt_value=decrypt)
        console.print(f"[cyan]{key}[/cyan]: {val or '(not set)'}")
    finally:
        db.close()


# Subreddits
@main.command("add-subreddit")
@click.argument("name")
@click.option("--sort", default="top", help="top | hot | new")
@click.option("--time", default="week", help="day | week | month | year | all")
@click.option("--limit", default=25, help="Posts to fetch per run")
def add_subreddit_cmd(name, sort, time, limit):
    """Add a subreddit to the monitor list."""
    db = SessionLocal()
    try:
        fetcher = StoryFetcher(db)
        settings = {"sort": sort, "time_filter": time, "limit": limit}
        sub = fetcher.add_subreddit(name, settings)
        console.print(f"[green]Added[/green] {sub.display_name}")
    finally:
        db.close()


@main.command("list-subreddits")
def list_subreddits_cmd():
    """Show all monitored subreddits."""
    db = SessionLocal()
    try:
        subs = db.query(Subreddit).all()
        table = Table(title="Monitored Subreddits")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Active", style="yellow")
        table.add_column("Fetch Settings", style="magenta")
        for s in subs:
            table.add_row(
                str(s.id), s.display_name, "Yes" if s.is_active else "No", str(s.fetch_settings)
            )
        console.print(table)
    finally:
        db.close()


# Fetching
@main.command("fetch")
@click.argument("subreddit_id", type=int)
def fetch_cmd(subreddit_id):
    """Fetch new stories from a single subreddit."""
    db = SessionLocal()
    try:
        fetcher = StoryFetcher(db)
        stories = fetcher.fetch_stories(subreddit_id)
        console.print(f"[bold green]Fetched {len(stories)} new stories[/bold green]")
        for st in stories:
            console.print(f"  • [dim]{st.title[:70]}{'...' if len(st.title) > 70 else ''}[/dim]")
    except Exception as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
    finally:
        db.close()


@main.command("fetch-all")
def fetch_all_cmd():
    """Fetch from every active subreddit."""
    db = SessionLocal()
    try:
        fetcher = StoryFetcher(db)
        results = fetcher.fetch_all_active()
        total = sum(len(v) for v in results.values())
        console.print(f"[bold green]Total new stories: {total}[/bold green]")
        for name, stories in results.items():
            console.print(f"  r/{name}: {len(stories)} stories")
    finally:
        db.close()


# Update Linking
@main.command("link-updates")
@click.option("--subreddit", default=None, help="Restrict linking to one subreddit")
def link_updates_cmd(subreddit):
    """Run the update-linking algorithm."""
    db = SessionLocal()
    try:
        linker = UpdateLinker(db)
        if subreddit:
            count = linker.link_updates_for_subreddit(subreddit)
        else:
            count = 0
            for (sub_name,) in db.query(Story.subreddit).distinct().all():
                count += linker.link_updates_for_subreddit(sub_name)
        console.print(f"[bold green]Linked {count} updates[/bold green]")
    finally:
        db.close()


@main.command("show-chain")
@click.argument("story_id", type=int)
def show_chain_cmd(story_id):
    """Display a story and its nested updates."""
    db = SessionLocal()
    try:
        linker = UpdateLinker(db)
        chain = linker.get_story_chain(story_id)
        if not chain:
            console.print("[red]Story not found[/red]")
            return

        console.print(f"[bold cyan]Original[/bold cyan]  u/{chain[0].author}  ↑{chain[0].score}")
        console.print(f"  {chain[0].title}")
        if len(chain) > 1:
            console.print(f"[bold yellow]Updates ({len(chain) - 1}):[/bold yellow]")
            for upd in chain[1:]:
                console.print(f"  → u/{upd.author}  ↑{upd.score}")
                console.print(f"    {upd.title}")
        else:
            console.print("[dim]No linked updates.[/dim]")
    finally:
        db.close()


# Stories
@main.command("list-stories")
@click.option("--limit", default=30, help="Max rows to show")
def list_stories_cmd(limit):
    """Browse stored stories."""
    db = SessionLocal()
    try:
        stories = db.query(Story).order_by(Story.fetched_at.desc()).limit(limit).all()
        table = Table(title="Recent Stories")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Title", style="green")
        table.add_column("Sub", style="yellow", no_wrap=True)
        table.add_column("Update", style="red", no_wrap=True)
        table.add_column("Video", style="blue", no_wrap=True)
        for s in stories:
            has_video = "Yes" if s.generated_video else "No"
            table.add_row(
                str(s.id),
                s.title[:55] + "..." if len(s.title) > 55 else s.title,
                s.subreddit,
                "Yes" if s.is_update else "No",
                has_video,
            )
        console.print(table)
    finally:
        db.close()


# Video Generation
@main.command("check-ffmpeg")
def check_ffmpeg_cmd():
    """Check FFmpeg installation."""
    path = find_ffmpeg()
    if path:
        version = get_ffmpeg_version(path)
        console.print(f"[green]FFmpeg found:[/green] {path}")
        console.print(f"[dim]{version}[/dim]")
    else:
        console.print("[red]FFmpeg not found![/red]")
        console.print("Install FFmpeg: https://ffmpeg.org/download.html")


@main.command("generate-video")
@click.argument("story_id", type=int)
@click.option("--tts-provider", default="openai", help="openai | elevenlabs")
@click.option("--tts-voice", default="alloy", help="Voice ID")
@click.option("--background", required=True, help="Path to video file or folder")
@click.option("--format", "video_format", default="shorts", help="shorts | normal")
@click.option("--include-updates/--no-include-updates", default=True, help="Include update stories")
@click.option("--subtitle-position", default="center", help="center | bottom | top")
@click.option("--subtitle-size", default=48, help="Font size for subtitles")
def generate_video_cmd(
    story_id,
    tts_provider,
    tts_voice,
    background,
    video_format,
    include_updates,
    subtitle_position,
    subtitle_size,
):
    """Generate a video from a story (CLI test for Phase 2)."""
    db = SessionLocal()
    try:
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            console.print("[red]Story not found[/red]")
            return

        if story.generated_video:
            console.print("[yellow]Video already exists. Delete it first to regenerate.[/yellow]")
            return

        mgr = SettingsManager(db)
        key_name = f"{tts_provider}_api_key"
        if not mgr.get(key_name, decrypt_value=True):
            console.print(f"[red]Error: {key_name} not set. Use: rva set-setting {key_name} <key> --encrypt[/red]")
            return

        ffmpeg_path = find_ffmpeg()
        if not ffmpeg_path:
            console.print("[red]FFmpeg not found. Install it first.[/red]")
            return

        console.print(f"[bold cyan]Generating video for:[/bold cyan] {story.title[:60]}...")
        console.print(f"  TTS: {tts_provider} / {tts_voice}")
        console.print(f"  Background: {background}")
        console.print(f"  Format: {video_format}")
        console.print()

        pipeline = VideoPipeline(db, ffmpeg_path=ffmpeg_path)

        style = SubtitleStyle(
            position=subtitle_position,
            font_size=subtitle_size,
        )

        def progress_cb(percent, step):
            console.print(f"  [{percent:3d}%] {step}")

        video = pipeline.generate(
            story_id=story_id,
            include_updates=include_updates,
            tts_provider=tts_provider,
            tts_voice=tts_voice,
            background_source=background,
            video_format=video_format,
            subtitle_style=style,
            progress_callback=progress_cb,
        )

        console.print()
        console.print(f"[bold green]✓ Video generated successfully![/bold green]")
        console.print(f"  Video: {video.video_path}")
        console.print(f"  Thumbnail: {video.thumbnail_path}")
        console.print(f"  Duration: {video.duration_seconds:.1f}s")
        console.print(f"  Size: {video.file_size_bytes / 1024 / 1024:.1f} MB")

    except VideoPipelineError as exc:
        console.print(f"[bold red]Pipeline Error:[/bold red] {exc}")
    except Exception as exc:
        console.print(f"[bold red]Unexpected Error:[/bold red] {exc}")
    finally:
        db.close()


@main.command("list-videos")
@click.option("--limit", default=30, help="Max rows to show")
def list_videos_cmd(limit):
    """Browse generated videos."""
    db = SessionLocal()
    try:
        videos = db.query(GeneratedVideo).order_by(GeneratedVideo.created_at.desc()).limit(limit).all()
        table = Table(title="Generated Videos")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Story", style="green")
        table.add_column("Format", style="yellow", no_wrap=True)
        table.add_column("Status", style="red", no_wrap=True)
        table.add_column("Progress", style="blue", no_wrap=True)
        table.add_column("YouTube", style="magenta", no_wrap=True)
        for v in videos:
            yt_status = v.youtube_upload_status
            if v.youtube_video_id:
                yt_status += f" ({v.youtube_video_id})"
            table.add_row(
                str(v.id),
                v.story.title[:40] + "..." if len(v.story.title) > 40 else v.story.title,
                v.format,
                v.status,
                f"{v.progress_percent}%",
                yt_status,
            )
        console.print(table)
    finally:
        db.close()


@main.command("video-progress")
@click.argument("video_id", type=int)
def video_progress_cmd(video_id):
    """Check video generation progress."""
    db = SessionLocal()
    try:
        pipeline = VideoPipeline(db)
        progress = pipeline.get_progress(video_id)
        console.print(f"[cyan]Video {video_id}[/cyan]")
        console.print(f"  Status: {progress['status']}")
        console.print(f"  Progress: {progress['progress_percent']}%")
        console.print(f"  Step: {progress['current_step']}")
        if progress['error_message']:
            console.print(f"  [red]Error: {progress['error_message']}[/red]")
    except VideoPipelineError as exc:
        console.print(f"[red]{exc}[/red]")
    finally:
        db.close()


# YouTube 
@main.group("youtube")
def youtube_group():
    """YouTube integration commands."""
    pass


@youtube_group.command("status")
def youtube_status_cmd():
    """Check YouTube OAuth status."""
    db = SessionLocal()
    try:
        auth = YouTubeAuthManager(db)
        console.print(f"[cyan]Configured:[/cyan] {'Yes' if auth.is_configured() else 'No'}")
        console.print(f"[cyan]Authenticated:[/cyan] {'Yes' if auth.is_authenticated() else 'No'}")
        if auth.is_authenticated():
            try:
                info = auth.get_user_info()
                console.print(f"[green]Logged in as:[/green] {info.get('name', 'Unknown')} ({info.get('email', 'N/A')})")
            except YouTubeAuthError as exc:
                console.print(f"[yellow]Could not fetch user info: {exc}[/yellow]")
    finally:
        db.close()


@youtube_group.command("set-credentials")
@click.argument("client_id")
@click.argument("client_secret")
def youtube_set_credentials(client_id, client_secret):
    """Store YouTube OAuth client credentials (encrypted)."""
    db = SessionLocal()
    try:
        mgr = SettingsManager(db)
        mgr.set("youtube_client_id", client_id, encrypt_value=True)
        mgr.set("youtube_client_secret", client_secret, encrypt_value=True)
        console.print("[green]YouTube OAuth credentials stored securely.[/green]")
        console.print("[dim]Next: run 'rva youtube auth-url' to get the login URL.[/dim]")
    finally:
        db.close()


@youtube_group.command("auth-url")
def youtube_auth_url_cmd():
    """Generate the Google OAuth consent URL."""
    db = SessionLocal()
    try:
        auth = YouTubeAuthManager(db)
        result = auth.initiate_auth_flow()
        console.print("[bold green]Open this URL in your browser:[/bold green]")
        console.print(result["auth_url"])
        console.print()
        console.print("[dim]After authorization, you will be redirected to localhost.[/dim]")
        console.print("[dim]Copy the 'code' query parameter and run:[/dim]")
        console.print(f"[yellow]rva youtube exchange-code <code> {result['state']}[/yellow]")
    except YouTubeAuthError as exc:
        console.print(f"[red]{exc}[/red]")
    finally:
        db.close()


@youtube_group.command("exchange-code")
@click.argument("code")
@click.argument("state")
def youtube_exchange_code(code, state):
    """Exchange the authorization code for tokens."""
    db = SessionLocal()
    try:
        auth = YouTubeAuthManager(db)
        auth.exchange_code(code=code, state=state)
        info = auth.get_user_info()
        console.print(f"[bold green]✓ YouTube account connected![/bold green]")
        console.print(f"  Name: {info.get('name', 'Unknown')}")
        console.print(f"  Email: {info.get('email', 'N/A')}")
        console.print(f"  Picture: {info.get('picture', 'N/A')}")
    except YouTubeAuthError as exc:
        console.print(f"[red]Auth failed: {exc}[/red]")
    finally:
        db.close()


@youtube_group.command("logout")
def youtube_logout_cmd():
    """Disconnect YouTube account and revoke tokens."""
    db = SessionLocal()
    try:
        auth = YouTubeAuthManager(db)
        auth.logout()
        console.print("[green]YouTube account disconnected.[/green]")
    except YouTubeAuthError as exc:
        console.print(f"[red]{exc}[/red]")
    finally:
        db.close()


@youtube_group.command("upload")
@click.argument("video_id", type=int)
@click.option("--title", default=None, help="Override video title")
@click.option("--description", default=None, help="Video description")
@click.option("--tags", default="", help="Comma-separated tags")
@click.option("--privacy", default="private", help="public | private | unlisted")
@click.option("--category", default="22", help="YouTube category ID")
@click.option("--thumbnail/--no-thumbnail", default=True, help="Upload custom thumbnail")
def youtube_upload_cmd(video_id, title, description, tags, privacy, category, thumbnail):
    """Upload a generated video to YouTube."""
    db = SessionLocal()
    try:
        video = db.query(GeneratedVideo).filter(GeneratedVideo.id == video_id).first()
        if not video:
            console.print("[red]Video not found[/red]")
            return

        if not Path(video.video_path).exists():
            console.print(f"[red]Video file missing: {video.video_path}[/red]")
            return

        auth = YouTubeAuthManager(db)
        if not auth.is_authenticated():
            console.print("[red]Not authenticated. Run 'rva youtube auth-url' first.[/red]")
            return

        meta = UploadMetadata(
            title=title or video.story.title,
            description=description or "",
            tags=[t.strip() for t in tags.split(",") if t.strip()],
            category_id=category,
            privacy_status=privacy,
        )

        console.print(f"[bold cyan]Uploading to YouTube:[/bold cyan] {meta.title[:60]}...")

        def progress_cb(percent, step):
            console.print(f"  [{percent:3d}%] {step}")

        uploader = YouTubeUploader(db)
        yt_id = uploader.upload_video(
            video_path=video.video_path,
            metadata=meta,
            video_record_id=video_id,
            progress_callback=progress_cb,
        )

        if thumbnail and video.thumbnail_path and Path(video.thumbnail_path).exists():
            try:
                uploader.upload_thumbnail(yt_id, video.thumbnail_path)
                console.print("[green]  Thumbnail uploaded.[/green]")
            except YouTubeUploadError as exc:
                console.print(f"[yellow]  Thumbnail upload failed: {exc}[/yellow]")

        video.youtube_video_id = yt_id
        video.youtube_upload_status = "uploaded"
        video.status = StoryStatus.UPLOADED.value
        db.commit()

        console.print()
        console.print(f"[bold green]✓ Uploaded successfully![/bold green]")
        console.print(f"  YouTube ID: {yt_id}")
        console.print(f"  URL: https://youtube.com/watch?v={yt_id}")

    except YouTubeUploadError as exc:
        console.print(f"[bold red]Upload Error:[/bold red] {exc}")
    except YouTubeAuthError as exc:
        console.print(f"[bold red]Auth Error:[/bold red] {exc}")
    except Exception as exc:
        console.print(f"[bold red]Unexpected Error:[/bold red] {exc}")
    finally:
        db.close()


@youtube_group.command("stats")
@click.argument("youtube_video_id")
def youtube_stats_cmd(youtube_video_id):
    """Fetch analytics for an uploaded YouTube video."""
    db = SessionLocal()
    try:
        auth = YouTubeAuthManager(db)
        if not auth.is_authenticated():
            console.print("[red]Not authenticated.[/red]")
            return

        manager = YouTubeManager(db)
        stats = manager.get_video_stats(youtube_video_id)

        table = Table(title=f"YouTube Stats: {stats.title[:50]}...")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Views", f"{stats.views:,}")
        table.add_row("Likes", f"{stats.likes:,}")
        table.add_row("Comments", f"{stats.comments:,}")
        table.add_row("Privacy", stats.privacy_status)
        table.add_row("Duration", stats.duration)
        table.add_row("Category", stats.category_id)
        table.add_row("Upload Date", stats.upload_date)
        console.print(table)

        console.print(f"[dim]Tags:[/dim] {', '.join(stats.tags[:10])}")

    except YouTubeManagerError as exc:
        console.print(f"[red]{exc}[/red]")
    except YouTubeAuthError as exc:
        console.print(f"[red]{exc}[/red]")
    finally:
        db.close()


@youtube_group.command("update-metadata")
@click.argument("youtube_video_id")
@click.option("--title", default=None, help="New title")
@click.option("--description", default=None, help="New description")
@click.option("--tags", default=None, help="Comma-separated tags")
@click.option("--category", default=None, help="Category ID")
def youtube_update_metadata_cmd(youtube_video_id, title, description, tags, category):
    """Edit metadata of an existing YouTube video."""
    db = SessionLocal()
    try:
        manager = YouTubeManager(db)
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        stats = manager.update_video_metadata(
            youtube_video_id=youtube_video_id,
            title=title,
            description=description,
            tags=tag_list,
            category_id=category,
        )
        console.print(f"[green]Updated:[/green] {stats.title}")
    except YouTubeManagerError as exc:
        console.print(f"[red]{exc}[/red]")
    finally:
        db.close()


@youtube_group.command("update-privacy")
@click.argument("youtube_video_id")
@click.argument("privacy_status")
def youtube_update_privacy_cmd(youtube_video_id, privacy_status):
    """Change the privacy status of a YouTube video."""
    db = SessionLocal()
    try:
        manager = YouTubeManager(db)
        stats = manager.update_privacy_status(youtube_video_id, privacy_status)
        console.print(f"[green]Privacy updated to {stats.privacy_status}[/green]")
    except YouTubeManagerError as exc:
        console.print(f"[red]{exc}[/red]")
    finally:
        db.close()


@youtube_group.command("delete")
@click.argument("youtube_video_id")
def youtube_delete_cmd(youtube_video_id):
    """Permanently delete a video from YouTube."""
    db = SessionLocal()
    try:
        manager = YouTubeManager(db)
        manager.delete_video(youtube_video_id)
        console.print(f"[green]Video {youtube_video_id} deleted from YouTube.[/green]")
    except YouTubeManagerError as exc:
        console.print(f"[red]{exc}[/red]")
    finally:
        db.close()


# Notifications
@main.command("notifications")
@click.option("--limit", default=20, help="Max rows to show")
@click.option("--unread-only", is_flag=True, help="Show only unread")
def notifications_cmd(limit, unread_only):
    """Show recent notifications."""
    db = SessionLocal()
    try:
        q = db.query(Notification).order_by(Notification.created_at.desc())
        if unread_only:
            q = q.filter(Notification.is_read.is_(False))
        notifs = q.limit(limit).all()

        if not notifs:
            console.print("[dim]No notifications.[/dim]")
            return

        table = Table(title="Notifications")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Type", style="yellow", no_wrap=True)
        table.add_column("Level", style="red", no_wrap=True)
        table.add_column("Message", style="green")
        table.add_column("Read", style="blue", no_wrap=True)
        table.add_column("Time", style="magenta", no_wrap=True)
        for n in notifs:
            table.add_row(
                str(n.id),
                n.type,
                n.level,
                n.message[:60] + "..." if len(n.message) > 60 else n.message,
                "✓" if n.is_read else "○",
                n.created_at.strftime("%Y-%m-%d %H:%M"),
            )
        console.print(table)
    finally:
        db.close()


@main.command("mark-read")
@click.argument("notification_id", type=int)
def mark_read_cmd(notification_id):
    """Mark a notification as read."""
    db = SessionLocal()
    try:
        n = db.query(Notification).filter(Notification.id == notification_id).first()
        if not n:
            console.print("[red]Notification not found[/red]")
            return
        n.is_read = True
        db.commit()
        console.print("[green]Marked as read.[/green]")
    finally:
        db.close()


if __name__ == "__main__":
    main()
