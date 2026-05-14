"""Reddit client using raw HTTP requests to old.reddit.com JSON endpoints.

No API keys or OAuth required. Uses httpx with polite delays and User-Agent rotation.
"""

import time
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field

import httpx
from sqlalchemy.orm import Session


class RedditClientError(Exception):
    pass


class RateLimitError(RedditClientError):
    """Raised when Reddit rate-limits us."""
    pass


@dataclass
class RateLimitStatus:
    """Tracks Reddit rate limit state from response headers."""
    remaining: int = 999
    reset_timestamp: float = 0.0
    used: int = 0
    last_request_at: float = 0.0

    @property
    def is_near_limit(self, threshold: int = 5) -> bool:
        return self.remaining <= threshold and self.remaining > 0

    @property
    def is_exhausted(self) -> bool:
        return self.remaining <= 0

    @property
    def reset_in_seconds(self) -> float:
        if self.reset_timestamp <= 0:
            return 0
        return max(0, self.reset_timestamp - time.time())

    @property
    def can_make_request(self) -> bool:
        return self.remaining > 0


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
    """HTTP-based Reddit client with fallback domains."""

    BASE_URL = "https://old.reddit.com"
    PRIMARY_URL = "https://old.reddit.com"
    FALLBACK_URL = "https://www.reddit.com"

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:126.0) Gecko/20100101 Firefox/126.0",
    ]

    def __init__(self, db: Session):
        self.db = db
        self._client: Optional[httpx.Client] = None
        self._ua_index = 0
        self._last_request_time: Optional[float] = None
        self._min_delay = 4.0
        self.rate_limit = RateLimitStatus()
        self._session_primed = False
        self._current_base = self.PRIMARY_URL

    def _get_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                headers=self._build_headers(),
                timeout=30.0,
                follow_redirects=True,
                cookies=httpx.Cookies(),
            )
            self._session_primed = False
        return self._client

    def _build_headers(self) -> dict:
        ua = self._next_ua()
        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

    def _next_ua(self) -> str:
        ua = self.USER_AGENTS[self._ua_index % len(self.USER_AGENTS)]
        self._ua_index += 1
        return ua

    def _polite_delay(self) -> None:
        if self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            if elapsed < self._min_delay:
                time.sleep(self._min_delay - elapsed)
        self._last_request_time = time.time()

    def _prime_session(self) -> None:
        """Get session cookies from homepage."""
        if self._session_primed:
            return
        try:
            client = self._get_client()
            resp = client.get(
                self._current_base,
                headers=self._build_headers(),
                timeout=10.0,
            )
            self._session_primed = True
            time.sleep(1.0)
        except Exception:
            pass

    def _update_rate_limit(self, headers: Dict[str, str]) -> None:
        try:
            if "x-ratelimit-remaining" in headers:
                self.rate_limit.remaining = int(float(headers["x-ratelimit-remaining"]))
            if "x-ratelimit-reset" in headers:
                self.rate_limit.reset_timestamp = float(headers["x-ratelimit-reset"])
            if "x-ratelimit-used" in headers:
                self.rate_limit.used = int(headers["x-ratelimit-used"])
            self.rate_limit.last_request_at = time.time()
        except (ValueError, TypeError):
            pass

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        self._polite_delay()
        
        if not self._session_primed:
            self._prime_session()
            
        client = self._get_client()

        try:
            resp = client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            raise RedditClientError(f"Network error: {exc}")

        self._update_rate_limit(dict(resp.headers))

        if resp.status_code == 429:
            reset_in = self.rate_limit.reset_in_seconds
            if reset_in > 0:
                raise RateLimitError(f"Rate limited. Try again in {int(reset_in)} seconds.")
            raise RateLimitError("Rate limited by Reddit. Please wait a few minutes before retrying.")

        if resp.status_code == 403:
            # Try fallback domain
            if self._current_base == self.PRIMARY_URL:
                self._current_base = self.FALLBACK_URL
                self._client = None
                self._session_primed = False
                self._polite_delay()
                try:
                    self._prime_session()
                    fresh = self._get_client()
                    fallback_url = url.replace(self.PRIMARY_URL, self.FALLBACK_URL)
                    resp2 = fresh.request(method, fallback_url, **kwargs)
                    if resp2.status_code == 200:
                        self._update_rate_limit(dict(resp2.headers))
                        return resp2
                except Exception:
                    pass
                finally:
                    self._current_base = self.PRIMARY_URL
            
            raise RedditClientError(
                f"Access denied (403). Reddit is blocking automated requests. "
                f"Try again later or use a different network."
            )

        if resp.status_code != 200:
            raise RedditClientError(f"Reddit returned HTTP {resp.status_code}: {resp.text[:200]}")

        return resp

    def test_connection(self) -> bool:
        try:
            resp = self._request("GET", f"{self.PRIMARY_URL}/r/AskReddit/.json", params={"limit": 1})
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
        after: Optional[str] = None,
    ) -> Tuple[List[RedditStory], Optional[str]]:
        url = f"{self._current_base}/r/{subreddit_name}/{sort}/.json"
        params: Dict[str, Any] = {"limit": limit}

        if sort in ("top", "controversial") and time_filter:
            params["t"] = time_filter

        if after:
            params["after"] = after

        resp = self._request("GET", url, params=params)

        try:
            data = resp.json()
        except Exception as exc:
            raise RedditClientError(f"Invalid JSON response: {exc}")

        if "error" in data:
            raise RedditClientError(f"Reddit error: {data['error']}")

        listing = data.get("data", {})
        children = listing.get("children", [])
        next_after = listing.get("after")

        stories: List[RedditStory] = []
        for child in children:
            post_data = child.get("data", {})
            if not post_data:
                continue
            stories.append(RedditStory(post_data))

        return stories, next_after

    def fetch_post_with_comments(
        self,
        permalink: str,
        limit: int = 50,
    ) -> Dict[str, Any]:
        # Use www.reddit.com for posts to avoid SSL cert issues on old.reddit.com
        url = f"{self.FALLBACK_URL}{permalink}.json"
        params = {"limit": limit}

        resp = self._request("GET", url, params=params)

        try:
            return resp.json()
        except Exception as exc:
            raise RedditClientError(f"Invalid JSON response: {exc}")

    def close(self) -> None:
        if self._client and not self._client.is_closed:
            self._client.close()

    def get_rate_limit_status(self) -> RateLimitStatus:
        return self.rate_limit


Submission = RedditStory