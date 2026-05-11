"""Reddit client using raw HTTP requests to old.reddit.com JSON endpoints.

No API keys or OAuth required. Uses httpx with polite delays and User-Agent rotation.
"""

import time
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session


class RedditClientError(Exception):
    pass


class RedditStory:
    """Lightweight data class mirroring PRAW Submission structure."""

    def __init__(self, data: Dict[str, Any]):
        self._data = data
        self.id = data.get("id", "")
        self.title = data.get("title", "")
        self.author = self._extract_author(data)
        self.score = data.get("score", 0)
        self.selftext = data.get("selftext", "")
        self.is_self = data.get("is_self", False)
        self.url = data.get("url", "")
        self.permalink = data.get("permalink", "")
        self.created_utc = data.get("created_utc", 0)

    def _extract_author(self, data: Dict[str, Any]) -> str:
        author_data = data.get("author")
        if isinstance(author_data, str):
            return author_data
        if isinstance(author_data, dict):
            return author_data.get("name", "[deleted]")
        return "[deleted]"


class RedditClient:
    """HTTP-based Reddit client targeting old.reddit.com JSON endpoints."""

    BASE_URL = "https://old.reddit.com"

    # Rotate through several realistic User-Agents
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    ]

    def __init__(self, db: Session):
        self.db = db
        self._client: Optional[httpx.Client] = None
        self._ua_index = 0
        self._last_request_time: Optional[float] = None
        self._min_delay = 2.0  # seconds between requests

    def _get_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                headers={"User-Agent": self._next_ua()},
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client

    def _next_ua(self) -> str:
        ua = self.USER_AGENTS[self._ua_index % len(self.USER_AGENTS)]
        self._ua_index += 1
        return ua

    def _polite_delay(self) -> None:
        """Enforce minimum delay between requests to avoid rate limits."""
        if self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            if elapsed < self._min_delay:
                time.sleep(self._min_delay - elapsed)
        self._last_request_time = time.time()

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Make a polite HTTP request with delay and error handling."""
        self._polite_delay()
        client = self._get_client()

        try:
            resp = client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            raise RedditClientError(f"Network error: {exc}")

        if resp.status_code == 429:
            # Rate limited — back off and retry once
            time.sleep(30)
            resp = client.request(method, url, **kwargs)

        if resp.status_code == 403:
            raise RedditClientError(
                f"Access denied (403). Reddit may be blocking this IP or User-Agent. "
                f"Try again later or use a different network."
            )

        if resp.status_code != 200:
            raise RedditClientError(
                f"Reddit returned HTTP {resp.status_code}: {resp.text[:200]}"
            )

        return resp

    def test_connection(self) -> bool:
        """Quick connectivity check."""
        try:
            resp = self._request("GET", f"{self.BASE_URL}/r/AskReddit/.json", params={"limit": 1})
            data = resp.json()
            return "data" in data and "children" in data["data"]
        except Exception:
            return False

    def fetch_subreddit_stories(
        self,
        subreddit_name: str,
        sort: str = "top",
        time_filter: str = "week",
        limit: int = 25,
    ) -> List[RedditStory]:
        """Fetch posts from a subreddit using old.reddit.com JSON endpoints."""

        # Build URL: /r/{sub}/{sort}/.json
        url = f"{self.BASE_URL}/r/{subreddit_name}/{sort}/.json"
        params: Dict[str, Any] = {"limit": limit}

        # Time filter only applies to top/controversial
        if sort in ("top", "controversial") and time_filter:
            params["t"] = time_filter

        resp = self._request("GET", url, params=params)

        try:
            data = resp.json()
        except Exception as exc:
            raise RedditClientError(f"Invalid JSON response: {exc}")

        if "error" in data:
            raise RedditClientError(f"Reddit error: {data['error']}")

        listing = data.get("data", {})
        children = listing.get("children", [])

        stories: List[RedditStory] = []
        for child in children:
            post_data = child.get("data", {})
            if not post_data:
                continue
            stories.append(RedditStory(post_data))

        return stories

    def fetch_post_with_comments(
        self,
        permalink: str,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Fetch a specific post and its comments."""
        url = f"{self.BASE_URL}{permalink}.json"
        params = {"limit": limit}

        resp = self._request("GET", url, params=params)

        try:
            return resp.json()
        except Exception as exc:
            raise RedditClientError(f"Invalid JSON response: {exc}")

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            self._client.close()


# Backwards-compatible alias for existing code
Submission = RedditStory