"""Thin PRAW wrapper with credential injection from encrypted DB settings."""

from typing import List, Optional

import praw
from praw.models import Submission
from sqlalchemy.orm import Session

from settings_manager import SettingsManager


class RedditClientError(Exception):
    pass


class RedditClient:
    def __init__(self, db: Session):
        self.db = db
        self._client: Optional[praw.Reddit] = None

    def _init_client(self) -> praw.Reddit:
        if self._client:
            return self._client

        settings = SettingsManager(self.db)
        client_id = settings.get("reddit_client_id", decrypt_value=True)
        client_secret = settings.get("reddit_client_secret", decrypt_value=True)
        user_agent = settings.get(
            "reddit_user_agent",
            default="RedditVideoAutomator/0.1 by /u/Username",
        )

        if not client_id or not client_secret:
            raise RedditClientError(
                "Reddit API credentials not configured. Use: rva set-setting reddit_client_id <id> --encrypt"
            )

        try:
            self._client = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
            )
            return self._client
        except Exception as exc:
            raise RedditClientError(f"Failed to initialize Reddit client: {exc}")

    def test_connection(self) -> bool:
        try:
            client = self._init_client()
            client.user.me()
            return True
        except Exception:
            return False

    def fetch_subreddit_stories(
        self,
        subreddit_name: str,
        sort: str = "top",
        time_filter: str = "week",
        limit: int = 25,
    ) -> List[Submission]:
        client = self._init_client()
        sub = client.subreddit(subreddit_name)

        try:
            if sort == "top":
                return list(sub.top(time_filter=time_filter, limit=limit))
            elif sort == "hot":
                return list(sub.hot(limit=limit))
            elif sort == "new":
                return list(sub.new(limit=limit))
            else:
                raise RedditClientError(f"Unsupported sort method: {sort}")
        except Exception as exc:
            raise RedditClientError(f"Failed to fetch r/{subreddit_name}: {exc}")