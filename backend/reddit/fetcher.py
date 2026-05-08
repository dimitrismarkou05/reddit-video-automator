"""Story fetching with deduplication, sanitization, and update-link triggering."""

import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple

from sqlalchemy.orm import Session

from models import Story, Subreddit, StoryStatus
from reddit.client import RedditClient, RedditClientError


def sanitize_subreddit_name(name: str) -> str:
    """Normalize and validate subreddit names to prevent injection."""
    name = name.strip().lower()

    # Strip URLs and prefixes
    name = re.sub(r"^(https?://)?(www\.)?reddit\.com/r/", "", name)
    name = re.sub(r"^r/", "", name)

    # Drop trailing path/query junk
    name = name.split("/")[0].split("?")[0]

    # Reddit allows a-z, 0-9, underscore; max 21 chars (we only validate chars here)
    if not re.match(r"^[a-z0-9_]+$", name):
        raise ValueError(f"Invalid subreddit name: {name!r}")

    return name


class StoryFetcher:
    def __init__(self, db: Session):
        self.db = db
        self.client = RedditClient(db)

    def add_subreddit(self, name: str, fetch_settings: Dict[str, Any] = None) -> Subreddit:
        sanitized = sanitize_subreddit_name(name)

        existing = self.db.query(Subreddit).filter(Subreddit.name == sanitized).first()
        if existing:
            return existing

        sub = Subreddit(
            name=sanitized,
            display_name=f"r/{sanitized}",
            fetch_settings=fetch_settings
            or {"sort": "top", "time_filter": "week", "limit": 25},
        )
        self.db.add(sub)
        self.db.commit()
        self.db.refresh(sub)
        return sub

    def fetch_stories(self, subreddit_id: int) -> List[Story]:
        sub = self.db.query(Subreddit).filter(Subreddit.id == subreddit_id).first()
        if not sub:
            raise ValueError(f"Subreddit id={subreddit_id} not found")

        settings = sub.fetch_settings or {}
        sort = settings.get("sort", "top")
        time_filter = settings.get("time_filter", "week")
        limit = settings.get("limit", 25)

        submissions = self.client.fetch_subreddit_stories(
            sub.name, sort=sort, time_filter=time_filter, limit=limit
        )

        stories: List[Story] = []
        for submission in submissions:
            # Deduplication: never fetch the same reddit_id twice
            exists = (
                self.db.query(Story).filter(Story.reddit_id == submission.id).first()
            )
            if exists:
                continue

            story = Story(
                reddit_id=submission.id,
                title=submission.title,
                author=submission.author.name if submission.author else "[deleted]",
                subreddit=sub.name,
                score=submission.score,
                body=submission.selftext if submission.is_self else None,
                url=submission.url,
                permalink=f"https://reddit.com{submission.permalink}",
                created_utc=datetime.fromtimestamp(submission.created_utc, tz=timezone.utc),
                status=StoryStatus.STORED.value,
            )
            self.db.add(story)
            stories.append(story)

        if stories:
            self.db.commit()
            # Trigger update linking for this subreddit
            self._link_updates_for_subreddit(sub.name)

        return stories

    def fetch_all_active(self) -> Tuple[Dict[str, List[Story]], Dict[str, str]]:
        """Fetch from every active subreddit. Returns (results, errors)."""
        results: Dict[str, List[Story]] = {}
        errors: Dict[str, str] = {}
        active = self.db.query(Subreddit).filter(Subreddit.is_active.is_(True)).all()

        for sub in active:
            try:
                results[sub.name] = self.fetch_stories(sub.id)
            except Exception as exc:
                results[sub.name] = []
                errors[sub.name] = str(exc)

        return results, errors

    def _link_updates_for_subreddit(self, subreddit_name: str) -> None:
        from reddit.linker import UpdateLinker

        linker = UpdateLinker(self.db)
        linker.link_updates_for_subreddit(subreddit_name)