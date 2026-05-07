import click
from rich.console import Console
from rich.table import Table
from sqlalchemy.orm import Session

from backend.database import SessionLocal, init_db
from backend.models import Story, Subreddit
from backend.reddit.fetcher import StoryFetcher
from backend.reddit.linker import UpdateLinker
from backend.settings_manager import SettingsManager

console = Console()


@click.group()
def main():
    """Reddit Video Automator CLI"""
    init_db()


@main.command("set-setting")
@click.argument("key")
@click.argument("value")
@click.option("--encrypt/--no-encrypt", default=False, help="Encrypt value at rest")
def set_setting(key, value, encrypt):
    """Store an application setting (e.g. reddit_client_id)."""
    db = SessionLocal()
    try:
        mgr = SettingsManager(db)
        mgr.set(key, value, encrypt_value=encrypt)
        console.print(f"[green]Set[/green] {key} {'(encrypted)' if encrypt else ''}")
    finally:
        db.close()


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
            console.print(f"\n[bold yellow]Updates ({len(chain) - 1}):[/bold yellow]")
            for upd in chain[1:]:
                console.print(f"  → u/{upd.author}  ↑{upd.score}")
                console.print(f"    {upd.title}")
        else:
            console.print("[dim]No linked updates.[/dim]")
    finally:
        db.close()


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
        for s in stories:
            table.add_row(
                str(s.id),
                s.title[:55] + "..." if len(s.title) > 55 else s.title,
                s.subreddit,
                "Yes" if s.is_update else "No",
            )
        console.print(table)
    finally:
        db.close()


if __name__ == "__main__":
    main()